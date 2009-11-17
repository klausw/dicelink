#!/usr/bin/env python2.5

import datetime
import logging
import re

from google.appengine.ext import db

### Data model
#
# Record sheets canonically live in the DB. Each sheet has a user-assiged
# name that does not need to be globally unique.
#
# When referring to a character by name, the following algorithm is used to locate it:
# - sheets within the current wave, including sub-wavelets
# - sheets defined by the blip's author
# - optional: sheets defined by other contributors of this wave (never dicelink)
#
# Access control:
# - follow Wave's model, don't let people retrieve from wavelets they would not themselves
#    have access to.
#
# Load sheet:
#    WHERE name=? AND wave=?
#    WHERE name=? AND owner=?

### Data in app engine
#
# Characters
#   ID/Name: id=1111
#  *name: "Hero"
#  *owner: "FOO@googlewave.com"
#   blip: "b+AaBbCcDdEe"
#  *wave: "googlewave.com!w+FfGgHhIi"
#   wavelet: "googlewave.com!conv+root"
#   text: "Name: Hero; Diplomacy: d20+17"
#
# Sheet (obsolescent, copy into "Characters" and set "migrated" flag)
#   ID/Name: name="Hero"
#   text: "Name: Hero; Diplomacy: d20+17"
#
# BlipMap
#   ID/Name: "name=char_Hero"
#   blip: "b+AaBbCcDdEe"
#   wave: "googlewave.com!w+FfGgHhIi"
#   wavelet: "googlewave.com!conv+root"
#
# DefaultChar
#   ID/Name: name="FOO@googlewave.com"
#   name: "MyCharacter"
#
# Msg
#   ID/Name: id=1001
#   author: "Klaus.Weidner"
#   content: "rolled d20: 8[8]
#   date: 2009-10-01 00:00:00.111222


FROM_FULL_URL_RE = re.compile(r'restored:wave:([^,]*)')
def canonical_campaign(campaign):
  m = FROM_FULL_URL_RE.search(campaign)
  if m:
    campaign = m.group(1)

  # Undo weird URL expansion
  campaign = campaign.replace('%252B', '+')
  campaign = campaign.replace('%2B', '+')
  return campaign

class Msg(db.Model):
  author = db.StringProperty()
  content = db.TextProperty()
  group = db.StringProperty(multiline=False)
  date = db.DateTimeProperty(auto_now_add=True)

def SaveMsg(user, text, group=''):
  Msg(author=user, content=text, group=group).put()

class BlipMap(db.Model):
  wave = db.StringProperty(multiline=False)
  wavelet = db.StringProperty(multiline=False)
  blip = db.StringProperty(multiline=False)

def SaveBlipMap(key, wave, wavelet, blip):
  BlipMap(key_name=key, wave=wave, wavelet=wavelet, blip=blip).put()

def GetBlipMap(key):
  item = BlipMap.get_by_key_name(key)
  if item:
    return item.wave, item.wavelet, item.blip
  else:
    return None, None, None

class Sheet(db.Model):
  text = db.TextProperty()

def SaveSheet(name, text):
  Sheet(key_name=name, text=text).put()

def GetSheet(name):
  sheet = Sheet.get_by_key_name(name)
  if sheet:
    return sheet.text
  else:
    return None

class DefaultChar(db.Model):
  # key: owner
  name = db.StringProperty(multiline=False)

def SetDefaultChar(user, char_name):
  DefaultChar(key_name=user, name=char_name).put()

def GetDefaultChar(user):
  entry = DefaultChar.get_by_key_name(user)
  if entry:
    return entry.name
  else:
    return None

class SearchList(db.Model):
  # key: wave
  searchlist = db.StringListProperty()

def SetSearchList(wave, list):
  SearchList(key_name=wave, searchlist=list).put()
  
def GetSearchList(wave):
  item = SearchList.get_by_key_name(wave)
  if not item:
    return []
  return item.searchlist

class Characters(db.Model):
  name = db.StringProperty(multiline=False)
  owner = db.StringProperty(multiline=False)
  wave = db.StringProperty(multiline=False)
  wavelet = db.StringProperty(multiline=False)
  blip = db.StringProperty(multiline=False)
  text = db.TextProperty()
  date = db.DateTimeProperty()

def CharactersInWave(wave):
  return Characters.all().filter('wave =', wave).count()

def FindCharacter(name, owner, wave, unused_wavelet):
  seen_chars = {}
  def seen(char):
    logging.debug('checking char %s, blip %s, key %s', char.name, char.blip, repr(char.key()))
    key = char.key()
    if key in seen_chars:
      return True
    seen_chars[key] = True
    return False

  for query in (Characters.all().filter('name =', name).filter('wave =', wave),
	        Characters.all().filter('name =', name).filter('owner =', owner)):
    results = query.order('-date').fetch(100)
    for result in results:
      if not seen(result):
	yield result

  # try again without sorting for uninitialized date fields
  for query in (Characters.all().filter('name =', name).filter('wave =', wave),
	        Characters.all().filter('name =', name).filter('owner =', owner)):
    results = query.fetch(100)
    for result in results:
      if not seen(result):
	logging.info('Yielding no-date character: key=%s, name=%s, owner=%s, wave=%s', result.key(), result.name, result.owner, result.wave)
	yield result

def GetCharacter(name, owner, wave, wavelet):
  for result in FindCharacter(name, owner, wave, wavelet):
    # get first, ignore the rest
    return result.text
  return None

def ClearCharacterForOwner(name, owner):
  deleted = 0
  for char in FindCharacter(name, owner, 'example.com!invalidWave', 'example.com!conv+root'):
    if char.owner == owner:
      char.delete()
      deleted += 1
  return 'cleared: %d' % deleted

def DeleteCharacterBlip(wave, wavelet, blip):
  for char in Characters.all().filter('wave =', wave).filter('wavelet =', wavelet).filter('blip =', blip).fetch(100):
    char.delete()

def SaveCharacter(name, owner, wave, wavelet, blip, text):
  # There Can Be Only One. Wipe cache of all other characters of this name in this wave (including
  # other wavelets) if saving in the toplevel wavelet, otherwise just affect the wavelet.
  # The goal is that the character you see is the character it'll use.

  # Update current blip, or make a new one
  char = Characters.all().filter('wave = ', wave).filter('wavelet =', wavelet).filter('blip =', blip).get()
  if not char:
    char = Characters()
  char.name = name
  char.owner = owner
  char.wave = wave
  char.wavelet = wavelet
  char.blip = blip
  char.text = text
  char.date = datetime.datetime.now()
  char.put()

  # Clear any other same-named characters in this wave (or wavelet). Should this be an error?
  char_query = Characters.all().filter('name =', name).filter('wave =', wave)
  if not '!conv+root' in wavelet:
    char_query = char_query.filter('wavelet =', wavelet)
  for old_char in char_query.fetch(100):
    if old_char.key() != char.key(): # don't delete myself
      old_char.delete()

