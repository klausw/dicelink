#!/usr/bin/env python2.5

import logging

from google.appengine.ext import db

import roll

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


class Msg(db.Model):
  author = db.StringProperty()
  content = db.StringProperty(multiline=False)
  date = db.DateTimeProperty(auto_now_add=True)

def SaveMsg(user, text):
  Msg(author=user, content=text).put()

def SaveNewRolls(user, text):
  out=[]
  for spec in roll.GetRollMatches(text):
    num, details = roll.RollDice(spec)
    out.append('rolled %s=%d [%s]' % (spec['spec'], num, details))
  SaveMsg(user, '; '.join(out))

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
  name = db.StringProperty(multiline=False)

def SetDefaultChar(user, char_name):
  DefaultChar(key_name=user, name=char_name).put()

def GetDefaultChar(user):
  entry = DefaultChar.get_by_key_name(user)
  if entry:
    return entry.name
  else:
    return None
