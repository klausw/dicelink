#!/usr/bin/env python2.5
import cgi
import logging
import os
import re
import urllib
import time

from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import charsheet
import controller
import roll
import eval
import persist
import charstore
import charstore_gae

import sys
sys.path.append('test')
import controller_test

FROM_FULL_URL_RE = re.compile(r'restored:wave:([^,]*)')

ANON_USER = 'Anonymous'
ANON_CAMPAIGN = 'Anonymous'

def canonical_campaign(campaign):
  m = FROM_FULL_URL_RE.search(campaign)
  if m:
    campaign = m.group(1)

  # Undo weird URL expansion
  campaign = campaign.replace('%252B', '+')
  campaign = campaign.replace('%2B', '+')
  return campaign

class MainPage(webapp.RequestHandler):
  def get(self):
    if users.get_current_user():
      url = users.create_logout_url('/')
      url_linktext = 'Logout'
      is_logged_in = True
      campaign = canonical_campaign(self.request.get('campaign', ANON_CAMPAIGN))
    else:
      url = users.create_login_url(self.request.uri)
      url_linktext = 'Login'
      is_logged_in = False
      campaign = ANON_CAMPAIGN

    try:
      msgs_query = persist.Msg.all().filter('group =', campaign)
      msgs = reversed(msgs_query.order('-date').fetch(20))
    except Exception, e:
      logging.warning('Got exception: %s', e)
      msgs = []

    title = 'DiceLink'
    if campaign != ANON_CAMPAIGN:
      title += ': Campaign: %s' % campaign

    template_values = {
      'title': title,
      'msgs': msgs,
      'url': url,
      'url_linktext': url_linktext,
      'is_logged_in': is_logged_in,
      'campaign': campaign,
      }

    path = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(path, template_values))

STRIP_ADDR_RE=re.compile(r'@.*')
STYLE_RE = re.compile(r'style/([a-z]*)([A-Z].*)?')

def UserInfo(campaign):
  current_user = users.get_current_user()
  if current_user:
    user = current_user.nickname()
    user = STRIP_ADDR_RE.sub('', user)
    email = current_user.email()
  else:
    user = ANON_USER
    email = 'Anonymous@example.com'

  wave_uid = STRIP_ADDR_RE.sub('@googlewave.com', email).lower()
  waveId = campaign
  waveletId = 'googlewave.com!conv+root' # FIXME!
  blipId = 'webBlip.%f' % time.time() 
  logging.debug('[]: wave_uid="%s", waveId="%s"' % (wave_uid, waveId))
  return user, waveId, waveletId, blipId

def CampaignPage(campaign):
  dest_url = '/'
  if campaign and campaign != ANON_CAMPAIGN:
    dest_url += '?campaign=' + urllib.quote_plus(campaign)
  return dest_url

class CharUpdateForm(webapp.RequestHandler):
  def get(self):
    campaign = canonical_campaign(self.request.get('campaign', ANON_CAMPAIGN))
    user, waveId, waveletId, blipId = UserInfo(campaign)
    name = self.request.get('name')
    storage = charstore_gae.GaeCharStore(user, user, waveId, waveletId, blipId)
    content = 'Name: '
    title = 'DiceLink: editing '
    if name:
      oldChar = storage.get(name)
      if oldChar:
	content = oldChar.text()
      else:
	content = 'Name: ' + name + '\n'
      title += name
    else:
      title += '(new character)'
      content = 'Name: ?\n'

    template_values = {
      'title': title,
      'campaign': campaign,
      'content': content,
      }

    path = os.path.join(os.path.dirname(__file__), 'editchar.html')
    self.response.out.write(template.render(path, template_values))

class CharUpdate(webapp.RequestHandler):
  def post(self):
    campaign = canonical_campaign(self.request.get('campaign', ANON_CAMPAIGN))
    user, waveId, waveletId, blipId = UserInfo(campaign)

    content = self.request.get('content') # not HTML escaped!

    if user == ANON_USER:
      return

    storage = charstore_gae.GaeCharStore(user, user, waveId, waveletId, blipId)

    sheet = charsheet.CharSheet(content)
    if sheet is not None:
      storage.put(sheet)
    self.redirect(CampaignPage(campaign))

class HTMLDoc(object):
  def __init__(self, text):
    self.text = text
    self.need_escape_start = [0]
    self.need_escape_end = []

  def annotate(self, start, end, texts):
    before = self.text[:start]
    after = self.text[end:]
    new = ''
    for rtxt in texts:
      txt = cgi.escape(rtxt[0])
      styles = []
      for anno, val in rtxt[1:]:
	m = STYLE_RE.match(anno)
	if m:
	  if m.group(2):
	    style = '%s-%s' % (m.group(1), m.group(2).lower())
	  else:
	    style = m.group(1)
	  styles.append('%s: %s' % (style, val))
      if styles:
	txt = '<span style="%s">%s</span>' % ('; '.join(styles), txt)
      new += txt
    self.text = before + new + after
    offset = len(new) - (end - start)
    self.need_escape_end.append(start)
    self.need_escape_start.append(end + offset)
    return offset

  def escape(self):
    if len(self.need_escape_start) > len(self.need_escape_end):
      self.need_escape_end.append(len(self.text))
    offset = 0
    for start, end in zip(self.need_escape_start, self.need_escape_end):
      # html escape the outside bits in replacer()
      offset += self.annotate(start+offset, end+offset, [[self.text[start+offset:end+offset]]])
    self.need_escape_start = []
    self.need_escape_end = []
    return self.text

class Roll(webapp.RequestHandler):
  def post(self):
    campaign = canonical_campaign(self.request.get('campaign', ANON_CAMPAIGN))
    user, waveId, waveletId, blipId = UserInfo(campaign)

    content = self.request.get('content') # not HTML escaped!

    if not '[' in content:
      content = '[' + content + ']'
    doc = HTMLDoc(content)

    # Assume replacements happen start to end
    def replacer(start, end, texts):
      return doc.annotate(start, end, texts)

    if user == ANON_USER:
      storage = charstore.CharStore()
    else:
      storage = charstore_gae.GaeCharStore(user, user, waveId, waveletId, blipId)

    controller.eval_expr(content, replacer, storage)

    persist.SaveMsg(user, doc.escape(), campaign)

    self.redirect(CampaignPage(campaign))

class RunTests(webapp.RequestHandler):
  def get(self):
    context = controller_test.MakeContext()
    for blip in controller_test.BlipIterator(context):
      hdr = '<small style="color: #888888">creator=%s, modifier=%s, waveId=%s, waveletId=%s, blipId=%s</small><br>' % (
	context['creator'], context['modifier'], context['waveId'], context['waveletId'], context['blipId'])
      self.response.out.write(hdr.encode('utf-8'))
      out = controller_test.doBlip(blip, context)
      out = out.replace('\n', '<br>\n')
      self.response.out.write(out.encode('utf-8'))
      self.response.out.write('<hr>')

application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                      ('/roll', Roll),
                                      #('/chars', CharList)],
                                      ('/char', CharUpdateForm),
                                      ('/charupdate', CharUpdate),
                                      ('/ftest', RunTests),
				     ],
                                     debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
