"""PV Rename

Usage:
    pvrename.py list [PATH] [--ext=<.db> ...]
    pvrename.py rename FILE [PATH] [--modify] [--diff=DIFF] [--diffargs=ARG ...]
    pvrename.py camelcase FILE
    pvrename.py caps FILE [--delim=<_> ...] [--ext=<.db> ...]

Options:
    --diff=DIFF    Diff program to use in dry-run mode [default: diff]
    --diffargs=Y   Diff arguments [default: -y]

List will simply find the db/template files and list all of the records
in the path.

Rename searches all of the files (excluding those in gitignore, build directories,
etc.) and replaces strings in the first column with the strings in the second.
These are not regular expressions but simple string replacements. Columns are either
tab or space delimited.

CamelCase/CAPS options will take a list of records and convert them between the two,
keeping macros intact. (e.g., CAP_MEAS_INPUT <-> CapMeasInput)
"""

from __future__ import print_function
import re
import os
import sys
import subprocess
import tempfile

import docopt


DEFAULT_EXT = ['.db', '.opi', '.edl', '.adl', '.cmd', '.template',
               '.proto', '.protocol', '.sub', '.substitutions']
DEF_CAPS_DELIM = ':)'
DEF_DELIM = '_'


def find_records(db_file):
    record_re = re.compile('[g]?record\s*\((.*),(.*)\)')
    for line in open(db_file, 'rt').readlines():
        line = line.strip()
        m = record_re.match(line)
        if m:
            rtyp, record = [s.strip() for s in m.groups()]
            rtyp = rtyp.strip('"').strip("'")
            record = record.strip('"').strip("'")
            yield (record, rtyp)


def load_ignore_file(fn):
    ret = []
    for line in open(fn, 'rt').readlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        line = line.replace('.', '\.')
        line = line.replace('*', '.*')
        line = '%s$' % line
        ret.append(line)

    return ret


def find_files(path='.', extensions=DEFAULT_EXT,
               ignore_paths=['/\.git/', '/\.svn/', '\/O\..*\/',
                             '\.sw[op]$', '\/db\/'],
               git_ignore='.gitignore'):

    git_ignore = os.path.join(path, git_ignore)
    if os.path.exists(git_ignore):
        ignore_paths.extend(load_ignore_file(git_ignore))

    ignore_paths = [re.compile(ignore) for ignore in ignore_paths]

    for root, dirs, files in os.walk(path):
        for fn in files:
            skip = False
            fn = os.path.join(root, fn)
            for ignore in ignore_paths:
                if ignore.search(fn) is not None:
                    skip = True
                    print('Skipping %s [matches %s]' % (fn, ignore.pattern),
                          file=sys.stderr)
                    break

            if skip:
                continue

            yield fn


def create_list(path, add_ext=[]):
    fns = list(find_files(path=path, extensions=DEFAULT_EXT + add_ext))

    db_files = [fn for fn in fns
                if os.path.splitext(fn)[1] in ('.db', '.template')]

    print('All database files:', file=sys.stderr)
    for fn in db_files:
        print('\t%s' % fn, file=sys.stderr)

    records = {}
    for fn in db_files:
        for record, rtyp in find_records(fn):
            records[record] = rtyp

    recs = list(records.keys())
    recs.sort(key=len, reverse=True)
    for record in recs:
        print(record)


def convert_case(fn, camel=True, delims=[], caps_delim=DEF_CAPS_DELIM):
    if not delims:
        delims = ['_', ]

    def to_camel(s):
        in_macro = False
        last_delim = False
        ret = []
        for c in s:
            if in_macro:
                if c == ')':
                    in_macro = False
                    if c in caps_delim:
                        last_delim = True
                ret.append(c)
                continue

            if c == '$':
                in_macro = True
                ret.append(c)
                continue

            if c in delims:
                last_delim = True
            elif c in caps_delim:
                last_delim = True
                ret.append(c)
            elif last_delim:
                c = c.upper()
                last_delim = False
                ret.append(c)
            else:
                c = c.lower()
                ret.append(c)

        return ''.join(ret)

    def to_caps(s):
        raise NotImplementedError

    for line in read_conv_file(fn):
        if not line:
            print()
        else:
            from_, to = line

            if from_ == to:
                if camel:
                    to = to_camel(to)
                else:
                    to = to_caps(to)

            print('%s\t%s' % (from_, to))


def read_conv_file(fn):
    line_re = re.compile('^(.*)\s+(.*)$')
    for line in open(fn, 'rt').readlines():
        line = line.strip()
        if not line:
            yield ()
            continue

        m = line_re.match(line)
        if m:
            from_, to = m.groups()
        else:
            from_, to = line, line

        yield (from_, to)


def rename(ren_fn, path, add_ext=[],
           dryrun=True, diff='diff', diff_args=[]):
    ren_fn = os.path.abspath(ren_fn)
    replace = list(read_conv_file(ren_fn))

    while '' in diff_args:
        diff_args.remove('')

    if add_ext is None:
        add_ext = []

    fns = list(find_files(path=path, extensions=DEFAULT_EXT + add_ext))
    for fn in fns:
        if os.path.abspath(fn) == ren_fn:
            continue

        text = open(fn, 'rt').read()
        orig_text = text

        for from_, to in replace:
            text = text.replace(from_, to)

        if text != orig_text:
            if dryrun:
                print('[dry run] Would change: %s' % fn)
                with tempfile.NamedTemporaryFile(mode='wt') as tempf:
                    tempf.write(text)
                    tempf.flush()

                    subprocess.call([diff, fn, tempf.name] + diff_args)

            else:
                open(fn, 'wt').write(text)


if __name__ == '__main__':
    arguments = docopt.docopt(__doc__, version='0.1')
    if arguments['list']:
        if arguments['PATH'] is None:
            arguments['PATH'] = '.'
        create_list(arguments['PATH'],
                    add_ext=arguments['--ext'])

    elif arguments['camelcase']:
        fn = arguments['FILE']
        convert_case(fn, camel=True,
                     delims=arguments['--delim'])

    elif arguments['caps']:
        fn = arguments['FILE']
        convert_case(fn, camel=False,
                     delims=arguments['--delim'])

    elif arguments['rename']:
        fn = arguments['FILE']
        if arguments['PATH'] is None:
            path = '.'
        else:
            path = arguments['PATH']
        rename(fn, path,
               add_ext=arguments['--ext'],
               dryrun=not arguments['--modify'],
               diff=arguments['--diff'],
               diff_args=arguments['--diffargs']
               )
