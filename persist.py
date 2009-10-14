#!/usr/bin/env python2.5

import logging

from google.appengine.ext import db

import roll

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
