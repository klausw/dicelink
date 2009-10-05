#!/usr/bin/env python2.5
import cgi
import os

from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import persist

class MainPage(webapp.RequestHandler):
  def get(self):
    msgs_query = persist.Msg.all().order('-date')
    msgs = reversed(msgs_query.fetch(20))

    if users.get_current_user():
      url = users.create_logout_url(self.request.uri)
      url_linktext = 'Logout'
    else:
      url = users.create_login_url(self.request.uri)
      url_linktext = 'Login'

    template_values = {
      'msgs': msgs,
      'url': url,
      'url_linktext': url_linktext,
      }

    path = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(path, template_values))

class Roll(webapp.RequestHandler):
  def post(self):
    if users.get_current_user():
      user = users.get_current_user().nickname()
    else:
      user = 'Anonymous'

    persist.SaveNewRolls(user, self.request.get('content'))
    self.redirect('/')


application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                      ('/roll', Roll)],
                                     debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
