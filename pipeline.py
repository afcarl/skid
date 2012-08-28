"""
Manage directory structure.

TODO:

  - pdftotext.txt should go in {cached}.d/data/

"""
import re, os, shutil
from debug import ip
from terminal import yellow, red, blue, green
from fsutils import mkdir, filetype
from web.download import download
from text.utils import htmltotext, remove_ligatures, force_unicode
from skid.config import CACHE
from hashlib import sha1

from skid.common import mergedict, unicodify_dict, dictsubset, parse_notes, \
    whitespace_cleanup

from pprint import pprint

import pdfutils


def cache_url(url):
    """
    Download url, write contents to file. Return filename of contents, None on
    failure to download.
    """
    # TODO: we should be telling download where to store stuff
    # explicitly... right now we just both have the same convention.
    cached = download(url, tries=1, pause=0.1, timeout=10, usecache=True,
                      cachedir=CACHE)
    if not cached:
        print 'Failed to download %s.' % url
        return

    return cached


def cache_document(src):
    "Cache a document, return filename of the cached file."

    # TODO: maybe support omitting 'http://', just guess that if its not a file
    # name it must be a url.

    # TODO:
    #  - make sure we don't overwrite files
    #  - cache to staging area first

    if src.startswith('http'):    # cache links
        return cache_url(src)

    elif os.path.exists(src):   # is this something on disk?

        dest = os.path.join(CACHE, os.path.basename(src))

        if os.path.exists(dest):
            print 'File %r already exists' % dest

            #raise Exception('File %r already exists' % dest)
            return dest

        shutil.copy2(src, dest)

        print 'copy:', src, '->', dest

        # TODO: What if the .d directory exists near the file already?
        return dest

    assert False


# TODO:
#
# - check if the directory already exists; maybe atomically write directory
#
# - dependencies between metadata to avoid recomputation; derived data versus
#   input (e.g. tags inferred by the system v. provided by user).
#
# - if it's a pdf we should try to get a bibtex entry for it.
#
# - grab any metadata available from pyPdf see from pdfutils.metadata import metadata
#
# - check document already exists
#
def add(source, tags='', title='', description='', interactive=True):
    """
    Import document from ``source``. Procedure will download/cache the file,
    create a directory to store metadta.
    """

    print blue % 'adding %s' % source

    assert ' ' not in source

    if isinstance(tags, basestring):
        tags = tags.split()
    tags = list(tags)

    # todo: maybe we should put the file in a staging area first so it won't
    # clobber anything (notes, cached document, etc)
    cached = cache_document(source)

    if not cached:  # failed to cache file
        print 'failed to cached file'
        return

    print cached

    d = Document(cached)

    d.hash_contents()
    d.extract_plaintext()

    old = d.extract_metadata()

    new = {
        'description': description.strip(),
        'title': title,
        'source': source,
        'cached': 'file://' + cached,
    }

    new = mergedict(old, new)

    if tags:
        # newtags will include all exisiting tags in the order the are listed in
        # document, concatenating new tags (ignoring duplicates; in order
        # listed).
        newtags = old['tags'].strip().split()
        existingtags = set(newtags)
        for t in tags:
            if t not in existingtags:
                newtags.append(t.strip())
        new['tags'] = ' '.join(newtags)


    new = unicodify_dict(new)
    old = unicodify_dict(old)

    existing = d.cached + '.d/notes.org'
    if os.path.exists(existing):
        existingdata = file(existing).read()
    else:
        existingdata = None

    newcontent = template(**new)

    if dictsubset(new, old):
        d.meta('notes.org', newcontent, overwrite=True)

    else:

        if newcontent.strip() != existingdata.strip():
            tmp = '/tmp/newmetadata.org'
            file(tmp, 'wb').write(newcontent)

            print yellow % '** old ************************'
            pprint(old)
            print yellow % '-- new ------------------------'
            pprint(new)
            print yellow % '*******************************'

#                raise AssertionError('Merging notes failed because existing notes '
#                                     'do not match new notes. Your intervention '
#                                     'try adding the paper again in interactive '
#                                     'mode.\n\n'
#                                     'kdiff3 %s %s' % (existing, tmp))

            print red % 'Need to merge descriptions...'
            print yellow % '=================================='
            if 0 != os.system('kdiff3 --merge %s %s --output %s' % (existing, tmp, existing)):
                print red % 'merge aborted. keeping original, other temporarily saved to %s' % tmp

                # todo: should probably delete any junk we might have done. This
                # is probably easier to do if we work in a staging area (we
                # might not even care to clean up after ourselves in that case).
                raise AssertionError('merging notes failed. aborting')
            else:
                print yellow % 'merge successful.'
                os.remove(existing + '.orig')  # remove kdiff's temporary file.

    if interactive:
        d.edit_notes()


class Document(object):

    def __init__(self, cached):
        self.cached = cached
        assert os.path.exists(cached)
        mkdir(cached + '.d')
        mkdir(cached + '.d/data')
        self.filetype = filetype(self.cached)

    def edit_notes(self):
        os.system('/home/timv/projects/env/bin/visit {self.cached}.d/notes.org'.format(self=self))

    def open(self):
        os.system('gnome-open {self.cached} 2>/dev/null'.format(self=self))

    def meta(self, name, content, overwrite=False):
        t = self.cached + '.d/' + name
        assert overwrite or not os.path.exists(t), name + ' already exists!'
        with file(t, 'wb') as f:
            content = force_unicode(content)
            content = content.encode('utf8')
            f.write(content)
            f.write('\n')    # new line at end of file
        return content

    def hash_contents(self):
        h = self.cached + '.d/data/hash'

        newhash = sha1(file(self.cached).read()).hexdigest()

        if os.path.exists(h):
            oldhash = file(h).read().strip()
        else:
            oldhash = newhash

        if newhash != oldhash:
            with file(h, 'wb') as f:
                f.write(newhash)
                f.write('\n')
            return newhash
        else:
            return oldhash

    def extract_metadata(self):

        metadata = {'tags': '', 'title': '', 'description': ''}
        if self.filetype.endswith('pdf'):

            # use pdfutils metadata extractor.
            pdfmeta = pdfutils.metadata(self.cached)
            if pdfmeta:
                if pdfmeta.get('title', None):
                    metadata['title'] = pdfmeta.get('title').strip()
                if pdfmeta.get('author', None):
                    metadata['author'] = pdfmeta.get('author').strip()

        # override anything automatic with user's notes file.

        existing = self.cached + '.d/notes.org'
        if os.path.exists(existing):
            notes = file(existing).read()
            metadata.update(parse_notes(notes))

        return metadata

    def extract_plaintext(self):
        "Extract plaintext from filename. Returns text, might cache."

        # TODO: doesn't work on my urls e.g. "http://google.com" b/c there's no ext.
        ext = os.path.splitext(self.cached)[1][1:]  # remove the dot

        if ext == 'pdf':
            # extract text from pdfs
            text = pdfutils.pdftotext(self.cached, verbose=True, usecached=True)

        else:
            with file(self.cached, 'r') as f:
                text = f.read()
            text = force_unicode(text)
            # clean up html
            text = htmltotext(text)

        text = remove_ligatures(text)

        return self.meta('data/text', text, overwrite=True)


def template(**kwargs):
    others = set(kwargs) - set('title source cached tags description'.split())
    attrs = '\n'.join(':%s: %s'.strip() for k in others).strip()
    if attrs:
        attrs += '\n'
    newdata = TEMPLATE.format(attrs=attrs, **kwargs)
    newdata = whitespace_cleanup(newdata)
    return force_unicode(newdata).encode('utf8').strip() + '\n'

TEMPLATE = u"""\
:title: {title}
:source: {source}
:cached: {cached}
:tags: {tags}
{attrs}
{description}
"""

