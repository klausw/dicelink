#!/usr/bin/env python2.5
import cgi
import logging
import os
import re
import urllib

from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import charsheet
import controller
import roll
import eval
import persist

FROM_FULL_URL_RE = re.compile(r'restored:wave:([^,]*)')

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
      url = users.create_logout_url(self.request.uri)
      url_linktext = 'Logout'
      is_logged_in = True
    else:
      url = users.create_login_url(self.request.uri)
      url_linktext = 'Login'
      is_logged_in = False

    campaign = self.request.get('campaign', 'None')
    campaign = canonical_campaign(campaign)

    try:
      msgs_query = persist.Msg.all().filter('group =', campaign)
      msgs = reversed(msgs_query.order('-date').fetch(20))
    except Exception, e:
      logging.warning('Got exception: %s', e)
      msgs = []

    template_values = {
      'msgs': msgs,
      'url': url,
      'url_linktext': url_linktext,
      'is_logged_in': is_logged_in,
      'campaign': campaign,
      }

    path = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(path, template_values))

STRIP_ADDR_RE=re.compile(r'@.*')

class Roll(webapp.RequestHandler):
  def post(self):
    current_user = users.get_current_user()
    if current_user:
      user = current_user.nickname()
      user = STRIP_ADDR_RE.sub('', user)
      email = current_user.email()
    else:
      user = 'Anonymous'
      email = 'Anonymous@example.com'
    content = self.request.get('content')
    campaign = self.request.get('campaign', 'None')
    campaign = canonical_campaign(campaign)

    if not '[' in content:
      content = '[' + content + ']'
    wave_uid = STRIP_ADDR_RE.sub('@googlewave.com', email).lower()
    waveId = campaign
    logging.debug('[]: wave_uid="%s", waveId="%s"' % (wave_uid, waveId))

    content = cgi.escape(content) # FIXME, <>& in expressions?
    out_msg = [content]
    def saver(sheet):
      pass
    def getter(name):
      logging.debug('Getter: name="%s"', name)
      sheet_txt = persist.GetCharacter(name, wave_uid, waveId)
      if sheet_txt:
	return charsheet.CharSheet(sheet_txt)
    def replacer(start, end, texts):
      new = out_msg[0][:start]
      for rtxt in texts:
        txt = rtxt[0]
	for anno, val in rtxt[1:]:
	  if anno == 'style/fontWeight':
	    txt = '<b>' + txt + '</b>'
	  elif anno == 'style/color':
	    txt = '<span style="color: %s">%s</span>' % (val, txt)
	new += txt
      new += out_msg[0][end:]
      out_msg[0] = new
      return len(new) - (end - start)
    def defaultgetter():
      return persist.GetDefaultChar(wave_uid)
    charsheet.SetCharacterAccessors(getter, saver)
    controller.handle_text(content, defaultgetter, replacer)
    persist.SaveMsg(user, out_msg[0], campaign)

    dest_url = '/'
    if campaign and campaign != 'None':
      dest_url += '?campaign=' + urllib.quote_plus(campaign)
    self.redirect(dest_url)


application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                      ('/roll', Roll)],
                                     debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
