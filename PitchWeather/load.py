# Load the XML data into a database
# If using sqlite, creates the necessary schema, too
# expects to find a gamedirs.yaml file,
# which was created by select_gamedirs.py

from BeautifulSoup import BeautifulStoneSoup
import os.path
import os
import sys
import pdb
import yaml
from dateutil import parser
import baseball

verbose = False

errorlog = open("baseball.err", "w")
nonamelog = open("unsaved_attrs.err", "w")

def get_start_date(gamedirs):
   """Look at files in all these dirs and return the earliest date."""
   def date_of(gamedir):
      datestring = BeautifulStoneSoup(open(os.path.join(gamedir, "boxscore.xml"))).findAll('boxscore')[0]['date']
      return dateutils.parse(datestring)

def loadbox(gamedirs):
   """Load game and box score data from game.xml, boxscore.xml
   Team names,  etc.
   Takes a list of directories, not just one, in case of suspensions."""

   #most info will be grabbed from the first
   gamefile = os.path.join(gamedirs[0], "game.xml")
   boxscorefile = os.path.join(gamedirs[0], "boxscore.xml")
   gamedata = BeautifulStoneSoup(open(gamefile))
   boxscoredata = BeautifulStoneSoup(open(boxscorefile))
   for teamdata in gamedata.findAll('team'):
      teamobj = xml2obj(teamdata.attrs, baseball.Team)
      if not baseball.session.query(baseball.Team).filter(baseball.Team.code == teamobj.code).all():
         baseball.session.add(teamobj)
         baseball.session.flush()
   gameobj = xml2obj(boxscoredata.findAll('boxscore')[0].attrs + gamedata.findAll('game')[0].attrs, baseball.Game)
   gameobj.game_pk = int(gameobj.game_pk)
   gameobj.start_date = get_start_date(gamedirs)
   baseball.session.add(gameobj)
   baseball.session.flush()
   return gameobj

players = {}
def loadplayers(playersfile, gameobj):
   """Load players.xml"""
   ids = {}
   playersdata  = BeautifulStoneSoup(open(playersfile))
   for team in playersdata.findAll('team'):
      for playerdata in team.findAll('player'):
         if playerdata['id'] in ids:
            print >>errorlog, "ignoring duplicate playerdata: %s from file %s" % (str(playerdata.attrs), playersfile)
            continue
         ids[playerdata['id']] = playerdata
         if playerdata['id'] not in players:
            playerobj  = xml2obj(playerdata.attrs, baseball.Player)
            baseball.session.add(playerobj)
            baseball.session.flush()
            players[playerdata['id']] = playerdata
         else:
not             pass

class DuplicatePitchError(RuntimeError):
   pass
class InningStructureError(RuntimeError):
   def __init__(self, offending_xml_file, inningdata, description):
      self.offending_xml_file = offending_xml_file
      self.inningdata =  inningdata
      self.description = description
class MissingFileError(RuntimeError):
   def __init__(self, directory, missing_file):
      self.directory = directory
      self.missing_file = missing_file
      self.value = "Looking for %s in %s" % (missing_file, directory)
   def __str__(self):
      return self.value


def check_innings(innings, pitchesfilename):
   """Takes a bunch of inning xml datasets.
   Sanity check. Does each inning have a top?
   Does each inning except possibly the last have a bottom?
   Does each atbat have some pitches?
   Return a list of atbats for the whole game.
   """
   for inningdata in innings:
      if len(inningdata.findAll('top')) != 1: 
         raise InningStructureError(pitchesfilename, inningdata, "missing top of inning")
   for inningdata in innings[:-1]:
      if len(inningdata.findAll('bottom')) != 1: 
         raise InningStructureError(pitchesfilename, inningdata, "missing bottom of inning")
   for inningdata in innings:
      for half in 'top', 'bottom':
         halfdata = inningdata.findAll(half)
         if halfdata:
            for atbatdata in halfdata[0].findAll('atbat'):
               if not atbatdata.findAll('pitch'):
                  #FIXME: an atbat will be skipped if a runner is picked off to end the inning before the first pitch.
                  # Is that desired behavior?
                  # Other cases where this could happen?
                  print >>errorlog, "skipping atbat %s because no pitches (dir %s)" % (atbatdata['num'], pitchesfilename)
               else:
                  atbatdata.attrs.append(('inning',  inningdata['num'])) # I like to refer to inning # in the same structure
                  yield atbatdata


def by_pitchcount(pitchdata1, pitchdata2):
   # Not all pitches have this field. Is id reliable? Or not sorting at all?
   return cmp(pitchdata1['tfs'], pitchdata2['tfs'])

def loadpitches(pitchesfile, gameobj):
   """Load at-bats and individual pitches and runner events
   from inning_all.xml"""

   def makepitchobj(pitchdata, count):
      pitchobj = xml2obj(pitchdata.attrs, baseball.Pitch)
      pitchobj.atbatnum = int(atbatdata['num'])
      pitchobj.batter = int(atbatdata['batter'])
      pitchobj.pitcher = int(atbatdata['pitcher'])
      pitchobj.game_pk = gameobj.game_pk
      pitchobj.payoff = False
      call = pitchdata['type']
      pitchobj.balls = count['balls']
      pitchobj.strikes = count['strikes']
      if call == 'B': count['balls'] += 1
      if call == 'S': count['strikes'] += 1
      return pitchobj

   filedata = BeautifulStoneSoup(open(pitchesfile))
   innings = filedata.findAll('inning')
   for atbatdata in check_innings(innings, pitchesfile):
      if verbose: print "\t", atbatdata['des']
      atbatobj = xml2obj(atbatdata.attrs, baseball.AtBat)
      atbatobj.game_pk = gameobj.game_pk
      print(parser.parse(atbatdata['start_tfs_zulu']))
      atbatobj.date = parser.parse(atbatdata['start_tfs_zulu']).date().ctime()
      baseball.session.add(atbatobj)
      pitch_datas = atbatdata.findAll('pitch')
      # pitch_datas.sort(by_pitchcount) # Make sure these are in order because...
      count = {'balls': 0, 'strikes': 0}
      for pitchdata in pitch_datas[:-1]:
         pitchobj = makepitchobj(pitchdata, count) # ...balls and strikes are counted as we go and...
         baseball.session.add(pitchobj)
      pitchdata = pitch_datas[-1] # ... and last one gets special treatment
      pitchobj = makepitchobj(pitchdata, count)
      pitchobj.payoff = True
      baseball.session.add(pitchobj)
      for runnerdata in atbatdata.findAll('runner'):
         runnerobj = xml2obj(runnerdata.attrs, baseball.Runner)
         runnerobj.atbatnum = atbatobj.num
         runnerobj.game_pk = gameobj.game_pk
         baseball.session.add(runnerobj)



def load_game_data(game_pk, gamedirs):
   """Check for files in gamedir and then load game metadata
   (By calling loadbox and loadplayers)
   Then load atbats and pitches.
   """
   gameobj = loadbox(gamedirs)
   for gamedir in gamedirs:
      loadplayers(os.path.join(gamedir, "players.xml"), gameobj)
   if verbose: print "loaded game metadata: ", gamedir
   load_atbats(gamedirs, gameobj)

def load_atbats(gamedirs, gameobj):
   game_pk = gameobj.game_pk
   for gamedir in gamedirs:
      loadpitches(os.path.join(gamedir, "inning", "inning_all.xml"), gameobj)
   if verbose: print "loaded at-bats and pitches: ", gamedirs

def load_games(session, gamedirs_file):
   gameinfos  =get_keys_and_dirs(gamedirs_file)
   for game_pk, gamedirs in gameinfos:
      load_game_data(game_pk, gamedirs)
   session.flush()
   session.commit()

def get_keys_and_dirs(gamedirs_file):
   """Takes the name of a yaml file mapping game primary keys to lists of directories for those games.

   Yields pairs of (key, [list of dirs])
   """
   for key, dirs in yaml.load(open(gamedirs_file)).iteritems():
      yield key, dirs

if __name__ == "__main__":
   if len(sys.argv) > 1:
      print "load.py doesn't recognize the argument -- use baseball.yaml"
   else:
      settings, session = baseball.init('baseball.yaml')
      gamedirs_file = settings['gamedirs_file']
      load_games(session, gamedirs_file)
