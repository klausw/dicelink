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

import logging
import re

import charsheet
import charstore
import eval
import roll

SETTINGS_BLIP_HEAD = '### DiceLink Settings ###'

EXPR_RE = re.compile(r'''
  \[
  (?: 
    ([^]:]*)
  : \s* )?
  ([^]]*)
  \]
  ''', re.X)

def is_settings(txt):
  idx = txt.find(SETTINGS_BLIP_HEAD)
  return (idx >= 0 and idx <= 2)

def parse_setting_line(line):
  colon_pos = line.find(':')
  comment_pos = line.find('#')
  if colon_pos < 0 or (comment_pos >= 0 and comment_pos < colon_pos):
    return (None, None, line)
  # don't strip off 
  cmd = line[0:colon_pos].strip()
  if comment_pos >= 0:
    return (cmd, line[colon_pos+1:comment_pos].strip(), line[comment_pos:])
  else:
    return (cmd, line[colon_pos+1:].strip(), None)

def apply_settings(txt, storage):
  config = {}
  for line in txt.split('\n'):
    cmd, arg, comment = parse_setting_line(line)
    if not cmd:
      continue
    if cmd == 'Inline rolls':
      if arg.lower() == 'true':
	config['inline'] = 'True'
      else:
	config['inline'] = 'False'
    if cmd == 'Import':
      imports = config.setdefault('imports', [])
      if comment:
	imports.append(arg + comment)
      else:
	imports.append(arg)
    if cmd == 'Global template':
      config['global'] = arg
  
  storage.setconfig(config)

# All values must be strings, use repr() serialized format
def process_text(txt, replacer, storage, optSheetTxt=None):
  if is_settings(txt):
    if optSheetTxt is not None:
      txt = optSheetTxt(True)
    logging.info('got settings: %s', txt)
    apply_settings(txt, storage)
  elif charsheet.isCharSheet(txt):
    if optSheetTxt is not None:
      txt = optSheetTxt(False)
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
      config = storage.getconfig() # lazy load configuration
      if config.get('inline') != 'True':
	return # ignore
      num, detail = roll.RollDice(spec)
      match_start = spec['start'] + offset
      match_end = spec['end'] + offset
      logging.info('inline: %s=%s (%s)', spec['spec'], num, detail)
      logging.debug('inline: @%d-%d in "%s"', match_start, match_end, txt)
      offset += replacer(match_start, match_end, [
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
    (?P<name> [^]:=]* )
    (?P<sep> :+)
  )?
  \s*
  (?P<expr> [^]]* )    # expression
  \]
  ''', re.X)

SPECIAL_EXPR_RE = re.compile(r'^\[ \! (.*) \]$', re.X)
STRINGS_RE = re.compile(r'"[^"]*?"')
PARENS_RE = re.compile(r'\([^()]*\)')
WORD_RE = re.compile(ur'([\w\u0080-\uffff]+)')
STRIKETHROUGH_RE = re.compile(r'\/\* (.*?) \*\/', re.X)

def already_evaluated(expr):
  expr = STRINGS_RE.sub('', expr)
  while True:
    new_expr = PARENS_RE.sub('', expr)
    if new_expr == expr:
      break
    expr = new_expr
  if '=' in expr and not '(' in expr:
    return True
  return False

# Cleanup: Wave leaves newlines annotated as links? Ignore everything
# after "\n", and ensure the preceding part has non-whitespace content.
def fix_anchor(full_txt, start, end):
  txt = full_txt[start:end]
  newline_pos = txt.find('\n')
  if newline_pos >= 0:
    txt = txt[:newline_pos]
    end = start + len(txt)
  if not txt.strip():
    end = start
  return start, end

def eval_expr(txt, replacer, storage):
  # calls replacer(start, end, texts) => offset_delta

  offset = 0
  for mexpr in EXPR_RE.finditer(txt):
    out_lst = []
    log_info = []
    expr = mexpr.group('expr').strip()
    if already_evaluated(expr) or 'Error:' in mexpr.group():
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

  special_fn = {
    'list': storage.list,
    'clear': storage.clear,
    'waveid': storage.waveid,
  }.get(cmd)
  if not special_fn:
    error('Unknown "[!" special command "%s"' % cmd)
    return out, logs
  logs.append('special: %s %s' % (expr, repr(arg)))
  # FIXME: special commands with prototype other than (charname)?
  # Commands taking a character arg 
  if cmd == 'waveid':
    arg = 'dummy'
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
    try:
      char = storage.get(charname)
    except charstore.Error, e:
      out.append(['%s ' % str(e), ('style/color', 'red')])
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
    error = None
    try:
      template = storage.get(template_name, template_location, template_key)
    except charstore.Error, e:
      error = '%s ' % str(e)
    if template:
      logging.debug('Using template "%s" for "%s"' % (template.name, char.name))
      for k, v in template.dict.iteritems():
	# don't overwrite existing entries
	sym.setdefault(k, v)
      log.append('template "%s" (%d),' % (template_name, len(template.dict)))
    else:
      if error is None:
	error = 'Template "%s" not found. ' % template_name
      if '!w' in template_name:
	error += 'Missing "@" before wave ID or link in _template? '
      out.append([error, ('style/color', 'red')])
  for k, v in DEFAULT_SYM.iteritems():
    sym.setdefault(k, v)

  # get global definitions for this wave
  config = storage.getconfig() # lazy load configuration
  globals_name = config.get('global', None)
  if globals_name:
    logging.info('Trying to load global sheet "%s"', globals_name)
    try:
      globals = storage.get(globals_name)
      if globals:
	logging.info('Using global sheet "%s" (%d)', globals_name, len(globals.dict))
	for k, v in globals.dict.iteritems():
	  sym.setdefault(k, v)
      else:
	out.append(['Global template "%s" not found. ' % globals_name, ('style/color', 'red')])
    except charstore.Error, e:
      out.append(['Global template: %s ' % str(e), ('style/color', 'red')])

  return sym, char, template, out, log

TRAILING_DIGIT_RE=re.compile(r'^(.*?)(\d+)$')

def get_expansions(expr, char, template):
  expansions = []
  if char:
    shortcuts = char.shortcuts
    if template:
      shortcuts.update(template.shortcuts)
    for ex in reversed(list(WORD_RE.finditer(expr))):
      word = ex.group()
      expand = char.shortcuts.get(word)
      if expand is None:
	m = TRAILING_DIGIT_RE.match(word)
	if m:
	  expand = char.shortcuts.get(m.group(1))
	  if expand:
	    expand = expand.replace('$', '')
	    expand += '(%s)' % m.group(2)
      #logging.info('expansion: w=%s, ex=%s', repr(ex.group()), repr(expand))
      if expand:
	expand = expand.replace('$', '')
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
  except (eval.ParseError, ValueError, TypeError, IndexError), e:
    txt = e.__class__.__name__ + ': ' + e.__str__()
    out.append([txt, ('style/color', 'red')])
    log.append(txt)
  return out, log

if __name__ == '__main__':
  import sys
  sys.path.append('test')
  import eval_test
  import mockblip
  logging.getLogger().setLevel(logging.DEBUG)
  eval.DEBUG_PARSER = True

  context = mockblip.MakeContext()
  for blip in sys.argv[1:]:
    if not '[' in blip:
      blip = '[' + blip + ']'
    print mockblip.doBlip(blip, context).encode('utf-8')
