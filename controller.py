import cgi
import logging
import re

import charsheet
import eval

EXPR_RE = re.compile(r'''
  \[
  (?: 
    ([^]:]*)
  : \s* )?
  ([^]]*)
  \]
  ''', re.X)

def handle_text(txt, defaultgetter, replacer):
  # calls replacer(start, end, texts) => offset_delta
  offset = 0
  for m in EXPR_RE.finditer(txt):
    out_lst = []
    if '=' in m.group(2) or 'ParseError' in m.group():
      continue
    char = None
    charname = None
    if m.group(1):
      charname = m.group(1)
    else:
      charname = defaultgetter()
    if charname:
      char = charsheet.GetChar(charname)
      if not char:
	out_lst.append(['"%s" not found' % charname, ('style/color', 'red')])

    out_lst += handle_expr(char, m.group(2))
    if out_lst:
      if char and not m.group(1):
	offset += replacer(m.start()+1+offset, m.start()+1+offset,
	  [[char.name + ':']])
      out_lst = [[' ']] + out_lst
      offset += replacer(m.end(2)+offset, m.end(2)+offset, out_lst)

def handle_expr(char, expr):
  log_info = []
  out_lst = []
  if char:
    sym = char.dict
    log_info.append('Char "%s" (%d),' % (char.name, len(char.dict)))
  else:
    sym = {}
  if '_template' in sym:
    template_name = sym['_template'].replace('"', '').strip()
    template = charsheet.GetChar(template_name)
    if template:
      logging.debug('Using template "%s" for "%s"' % (template.name, char.name))
      for k, v in template.dict.iteritems():
	sym.setdefault(k, v)
      log_info.append('template "%s" (%d),' % (template_name, len(template.dict)))
    else:
      logging.debug('template "%s" for "%s" not found' % (template_name, char.name))
  env = {
    'opt_nat20': True,
    'opt_crit_notify': int(sym.get('_critNotify', sym.get('CritNotify', 20))),
  }
  try:
    log_info.append('"%s":' % expr)
    for result in eval.ParseExpr(expr, sym, env):
      if out_lst:
	out_lst.append([', '])
      else:
	log_info.append(repr(result.stats))
      detail=''
      value=''
      # use cgi.escape() to prevent XSS from user-supplied string tags
      if '_secret' in sym or 'Secret' in sym:
	value = result.secretval()
	out_lst.append([cgi.escape(result.secretval()), ('style/fontWeight', 'bold')])
      else:
	detail = result.detail()
	value = cgi.escape(result.publicval())
      out_lst.append([detail+'=', ('style/color', '#aa00ff')])
      out_lst.append([value, ('style/fontWeight', 'bold')])
      log_info.append('%s=%s' % (detail, value))
  except eval.ParseError, e:
    out_lst.append([str(e), ('style/color', 'red')])
    log_info.append(str(e))
  logging.info(' '.join(log_info))
  return out_lst
