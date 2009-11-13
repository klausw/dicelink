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
      campaign = self.request.get('campaign', ANON_CAMPAIGN) 
      campaign = canonical_campaign(campaign)
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

    title = ''
    if campaign != ANON_CAMPAIGN:
      title = '<h1>Campaign: %s</h1>' % campaign

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
    content = self.request.get('content') # not HTML escaped!
    campaign = self.request.get('campaign', ANON_CAMPAIGN)
    campaign = canonical_campaign(campaign)

    if not '[' in content:
      content = '[' + content + ']'
    wave_uid = STRIP_ADDR_RE.sub('@googlewave.com', email).lower()
    waveId = campaign
    logging.debug('[]: wave_uid="%s", waveId="%s"' % (wave_uid, waveId))

    out_msg = [content]

    def saver(sheet):
      pass
      
    def getter(name):
      logging.debug('Getter: name="%s"', name)
      sheet_txt = persist.GetCharacter(name, wave_uid, waveId)
      if sheet_txt:
	return charsheet.CharSheet(sheet_txt)

    # Assume replacements happen start to end
    need_escape_start = [0]
    need_escape_end = []
    def replacer(start, end, texts):
      before = out_msg[0][:start]
      after = out_msg[0][end:]
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
      out_msg[0] = before + new + after
      offset = len(new) - (end - start)
      need_escape_end.append(start)
      need_escape_start.append(end + offset)
      return offset

    def defaultgetter():
      return persist.GetDefaultChar(wave_uid)

    def defaultsetter(name):
      if user != 'Anonymous':
	persist.SetDefaultChar(wave_uid, name)

    storage = charsheet.CharacterAccessor(getter, saver)
    controller.handle_text(content, defaultgetter, defaultsetter, replacer, storage)

    need_escape_end.append(len(out_msg[0]))
    offset = 0
    for start, end in zip(need_escape_start, need_escape_end):
      # html escape the outside bits in replacer()
      offset += replacer(start+offset, end+offset, out_msg[0][start+offset:end+offset])
    persist.SaveMsg(user, out_msg[0], campaign)

    dest_url = '/'
    if campaign and campaign != ANON_CAMPAIGN:
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
