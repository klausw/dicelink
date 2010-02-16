#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import re

import charsheet
import eval
import roll

EXPR_RE = re.compile(r'''
  \[
  (?: 
    ([^]:]*)
  : \s* )?
  ([^]]*)
  \]
  ''', re.X)

def process_text(txt, replacer, storage):
  if charsheet.isCharSheet(txt):
    char = charsheet.CharSheet(txt)
    if char:
      logging.info('save char sheet, name="%s", keys=%d, bytes=%d', char.name, len(char.dict), len(txt))
      storage.put(char)
      storage.setdefault(char.name)
  elif '[' in txt:
    eval_expr(txt, replacer, storage)
  else: # legacy inline XdS+N syntax
    offset = 0
    for spec in roll.GetRollMatches(txt):
      num, detail = roll.RollDice(spec)
      logging.info('inline: %s=%s (%s)', spec['spec'], num, detail)
      match_start = spec['start'] + offset
      match_end = spec['end'] + offset
      offset += SetTextWithAttributes(doc, match_start, match_end, [
	[spec['spec'], ('style/color', '#aa00ff')],
	['=%d' % num, ('style/fontWeight', 'bold')],
	[' ('],
	[detail, ('style/color', 'gray')],
	[')'],
      ])
      #out_private.append('%s rolled %s: %d [%s]' % (modifier, spec['spec'], num, detail))
      #persist.SaveMsg(modifier, 'rolled %s: %d [%s]' % (spec['spec'], num, detail))

DEFAULT_SYM = {
  '$x': eval.Function(['__n'], 'repeat(__n, $)'),
}

EXPR_RE = re.compile(r'''
  \[
  (?:        # "CharacterName:", optional
    \s*
    (?P<name> [^]:]* )
    (?P<sep> :+)
  )?
  \s*
  (?P<expr> [^]]* )    # expression
  \]
  ''', re.X)

SPECIAL_EXPR_RE = re.compile(r'^\[ \! (.*) \]$', re.X)
PARENS_RE = re.compile(r'\(.*\)')
WORD_RE = re.compile(ur'([\w\u0080-\uffff]+)')
STRIKETHROUGH_RE = re.compile(r'\/\* (.*?) \*\/', re.X)

def eval_expr(txt, replacer, storage):
  # calls replacer(start, end, texts) => offset_delta

  offset = 0
  for mexpr in EXPR_RE.finditer(txt):
    out_lst = []
    log_info = []
    expr = mexpr.group('expr').strip()
    expr_outside_parens = PARENS_RE.sub('', expr)
    if '=' in expr_outside_parens or 'Error:' in mexpr.group():
      continue
    charname = None
    char = None
    expansions = []
    name_match = mexpr.group('name')
    name_start = mexpr.start()+1
    expr_start = mexpr.start('expr')
    expr_end = mexpr.end('expr')

    #logging.debug('charname=%s expr=%s', repr(charname), repr(expr))
    maybe_special = SPECIAL_EXPR_RE.match(mexpr.group())
    if maybe_special:
      # "[:" prefix for special commands
      out, log = do_special(storage, maybe_special.group(1).strip())
      out_lst += out
      log_info += log
    else:
      if name_match is not None:
	charname = name_match.strip()
	if mexpr.group('sep') == '::':
	  storage.setdefault(charname)
	# "[:" disables the default char for this roll by setting charname=''
      else:
	charname = storage.getdefault()
      # charname==None or charname=='' mean no default char

      sym, char, template, out, log = get_char_and_template(storage, charname)
      out_lst += out
      log_info += log

      expr, expansions = get_expansions(expr, char, template)

      out, log = handle_expr(sym, expr)
      out_lst += out
      log_info += log

    if out_lst:
      if char and not name_match:
	offset += replacer(name_start+offset, name_start+offset,
	  [[char.name + ':']])
      for expand, start, end in expansions:
        offset += replacer(expr_start + start + offset, expr_start + end + offset, [[expand]])

      out_lst = [[' ']] + out_lst
      offset += replacer(expr_end+offset, expr_end+offset, out_lst)

    if log_info:
      logging.info(' '.join(log_info))

def do_special(storage, expr):
  out = []
  logs = []

  def error(msg):
    out.append(['Error: ' + msg, ('style/color', 'red')])
    logs.append(msg)
    
  m = WORD_RE.match(expr)
  if not m:
    error('Missing command after "[!"')
    return out, logs

  cmd = m.group(1)
  arg = expr[m.end():].strip()

  special_fn = {'list': storage.list, 'clear': storage.clear}.get(cmd)
  if not special_fn:
    error('Unknown "[!" special command "%s"' % cmd)
    return out, logs
  logs.append('special: %s %s' % (expr, repr(arg)))
  # FIXME: special commands with prototype other than (charname)?
  # Commands taking a character arg 
  if not arg:
    error('Usage: "[!%s CharacterName]"' % cmd)
    return out, logs
  out.append(['=', ('style/color', '#aa00ff')])
  for msg, log in special_fn(arg):
    if msg:
      out.append(msg)
    if log:
      logs.append(log)
  return out, logs

TEMPLATE_AT_RE = re.compile(r'^(.*?) \s* @ \s* (.*?) (?: \s* = \s* (.*?) \s*)?$', re.X)

def get_char_and_template(storage, charname):
  out = []
  log = []
  sym = {}
  char = None
  if charname:
    char = storage.get(charname)
    if char:
      sym = char.dict
      log.append('Char "%s" (%d),' % (char.name, len(char.dict)))
    else:
      out.append(['Sheet "%s" not found. ' % charname, ('style/color', 'red')])

  template = None
  if '_template' in sym:
    template_name = sym['_template'].replace('"', '').strip()
    template_location = None
    template_key = None
    m = TEMPLATE_AT_RE.search(template_name)
    if m:
      template_name = m.group(1)
      template_location = m.group(2)
      template_key = m.group(3)
    template = storage.get(template_name, template_location, template_key)
    if template:
      logging.debug('Using template "%s" for "%s"' % (template.name, char.name))
      for k, v in template.dict.iteritems():
	# don't overwrite existing entries
	sym.setdefault(k, v)
      log.append('template "%s" (%d),' % (template_name, len(template.dict)))
    else:
      out.append(['Template "%s" not found. ' % template_name, ('style/color', 'red')])
  for k, v in DEFAULT_SYM.iteritems():
    sym.setdefault(k, v)
  return sym, char, template, out, log

def get_expansions(expr, char, template):
  expansions = []
  if char:
    shortcuts = char.shortcuts
    if template:
      shortcuts.update(template.shortcuts)
    for ex in reversed(list(WORD_RE.finditer(expr))):
      expand = char.shortcuts.get(ex.group())
      #logging.debug('expansion: w=%s, ex=%s', repr(ex.group()), repr(expand))
      if expand:
	expr = expr[:ex.start()] + expand + expr[ex.end():]
	expansions.append((expand, ex.start(), ex.end()))
    defaults = shortcuts.get('DEFAULTS')
    if defaults is not None:
      expr = defaults + ' ' + expr
      
  return expr, reversed(expansions)

def markup(txt):
  out = []
  pos = 0
  for m in STRIKETHROUGH_RE.finditer(txt):
    out.append([txt[pos:m.start()], ('style/color', '#aa00ff')])
    out.append([m.group(1), ('style/color', '#cc88ff'), ('style/textDecoration', 'line-through')]) 
    pos = m.end()
  out.append([txt[pos:], ('style/color', '#aa00ff')])
  return out

def handle_expr(sym, expr):
  out = []
  log = []
  env = {
    'opt_nat20': True,
    'opt_crit_notify': int(sym.get('_critNotify', sym.get('CritNotify', 20))),
  }
  try:
    log.append('[%s]:' % expr)
    raw_result = eval.ParseExpr(expr, sym, env)
    if raw_result.show_as_list():
      results = raw_result.items()
    else:
      results = [raw_result]
    for result in results:
      if out:
	out.append([', '])
      else:
	log.append(repr(result.stats))
      detail=''
      value=''
      # callers may need to use cgi.escape() to prevent XSS from user-supplied string tags?
      if '_secret' in sym or 'Secret' in sym:
	value = result.secretval()
      else:
      	value = result.publicval()
	detail = result.detail()
      detail += '='
      out += markup(detail)
      out.append([value, ('style/fontWeight', 'bold')])
      log.append(detail + value)
  except eval.ParseError, e:
    out.append([e.__str__(), ('style/color', 'red')])
    log.append(e.__str__())
  return out, log

