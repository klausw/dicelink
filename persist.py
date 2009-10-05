#!/usr/bin/env python2.5

from google.appengine.ext import db

import roll

class Msg(db.Model):
  author = db.StringProperty()
  content = db.StringProperty(multiline=False)
  date = db.DateTimeProperty(auto_now_add=True)

def SaveMsg(user, text):
  msg = Msg()
  msg.author = user
  msg.content = text
  msg.put()

def SaveNewRolls(user, text):
  out=[]
  for spec in roll.GetRollMatches(text):
    num, details = roll.RollDice(spec)
    out.append('rolled %s=%d [%s]' % (spec['spec'], num, details))
  SaveMsg(user, '; '.join(out))
