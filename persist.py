#!/usr/bin/env python2.5

# Copyright 2009, 2010 Klaus Weidner <klausw@google.com>
# 
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
# 
#        http://www.apache.org/licenses/LICENSE-2.0
# 
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import datetime
import logging

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
# WaveConfig
#   # one per wave
#   Id/Name: "googlewave.com!w+FfGgHhIi"
#   settings: StringList
#     "key=value" strings
#
# SearchList
#   # one per wave
#   searchlist: StringList
#     "@WaveId#comment" strings
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
# DefaultChar
#   ID/Name: name="FOO@googlewave.com"
#   name: "MyCharacter"
#
# Msg
#   ID/Name: id=1001
#   author: "Klaus.Weidner"
#   content: "rolled d20: 8[8]
#   date: 2009-10-01 00:00:00.111222

class WaveConfig(db.Model):
  settings = db.StringListProperty()

class SearchList(db.Model):
  searchlist = db.StringListProperty()

def getWaveId(raw):
  start = 0
  end = len(raw)

  at_pos = raw.find('@')
  if at_pos >= 0:
    start = at_pos + 1

  comment_pos = raw.find('#')
  if comment_pos >= 0:
    end = comment_pos

  return raw[start:end].strip()

def GetSearchList(waveId):
  if not waveId:
    # malformed: "_template: Name @"
    return []
  search = SearchList.get_by_key_name(waveId)
  if search:
    lst = [waveId] + [getWaveId(x) for x in search.searchlist]
    logging.info('GetSearchList: %s', repr(lst))
    return lst
  else:
    return [waveId]

def GetConfig(waveId, defaults):
  config = defaults.copy()
  entry = WaveConfig.get_by_key_name(waveId)
  if not entry:
    return config
  for entry in entry.settings:
    item = entry.split('=')
    if len(item) == 1:
      config[item[0]] = True
    else:
      config[item[0]] = item[1]
  search = SearchList.get_by_key_name(waveId)
  if search:
    config['imports'] = search.searchlist
  return config

def SaveConfig(waveId, config):
  lst = []
  imports = []
  for (key, value) in config.iteritems():
    if key == 'imports':
      imports = value
    else:
      lst.append('%s=%s' % (key, value))
  WaveConfig(key_name=waveId, settings=lst).put()
  SearchList(key_name=waveId, searchlist=imports).put()
  logging.info('config saved for wave %s: settings=%s, imports=%s', waveId, repr(lst), repr(imports))

class Msg(db.Model):
  author = db.StringProperty()
  content = db.TextProperty()
  group = db.StringProperty(multiline=False)
  date = db.DateTimeProperty(auto_now_add=True)

def SaveMsg(user, text, group=''):
  Msg(author=user, content=text, group=group).put()

#class BlipMap(db.Model):
#  wave = db.StringProperty(multiline=False)
#  wavelet = db.StringProperty(multiline=False)
#  blip = db.StringProperty(multiline=False)
#
#def SaveBlipMap(key, wave, wavelet, blip):
#  BlipMap(key_name=key, wave=wave, wavelet=wavelet, blip=blip).put()
#
#def GetBlipMap(key):
#  item = BlipMap.get_by_key_name(key)
#  if item:
#    return item.wave, item.wavelet, item.blip
#  else:
#    return None, None, None

class DefaultChar(db.Model):
  name = db.StringProperty(multiline=False)

def SetDefaultChar(user, char_name):
  DefaultChar(key_name=user, name=char_name).put()

def GetDefaultChar(user):
  entry = DefaultChar.get_by_key_name(user)
  if entry:
    return entry.name
  else:
    return None

class Characters(db.Model):
  name = db.StringProperty(multiline=False)
  owner = db.StringProperty(multiline=False)
  wave = db.StringProperty(multiline=False)
  wavelet = db.StringProperty(multiline=False)
  blip = db.StringProperty(multiline=False)
  text = db.TextProperty()
  date = db.DateTimeProperty()

def FindCharacter(name, owner, wave, unused_wavelet):
  seen_chars = {}
  def seen(char):
    logging.debug('checking char %s, blip %s, key %s', char.name, char.blip, repr(char.key()))
    key = char.key()
    if key in seen_chars:
      return True
    seen_chars[key] = True
    return False

  for wave in GetSearchList(wave):
    query = Characters.all().filter('name =', name).filter('wave =', wave)
    results = query.fetch(100)
    for result in results:
      if not seen(result):
	yield result

  query = Characters.all().filter('name =', name).filter('owner =', owner)
  results = query.fetch(100)
  for result in results:
    if not seen(result):
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

  # Update current blip's character, or make a new one
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

