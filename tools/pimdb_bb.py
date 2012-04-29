##
## Created       : Sat Apr 07 18:52:19 IST 2012
## Last Modified : Sun Apr 29 12:27:30 IST 2012
##
## Copyright (C) 2012 by Sriram Karra <karra.etc@gmail.com>
##
## Licensed under the GPL v3
##

import codecs, datetime, logging, re, time
from   pimdb        import PIMDB
from   folder       import Folder
from   folder_bb    import BBContactsFolder
from   contact_bb   import BBContact

## Note: Each BBDB File is a message store and there are one or more folders
## in it.
class MessageStore:
    """Represents a physical BBDB file, made up of one or more folders,
    each containing contacts."""

    def __init__ (self, db, name):
        self.atts = {}
        self.set_db(db)
        self.set_name(name)
        self._set_regexes()
        self.set_folders({})

        self.populate_folders()

    ##
    ## Some get and set routines
    ##

    def _get_att (self, key):
        return self.atts[key]

    def _set_att (self, key, val):
        self.atts[key] = val
        return val

    def get_db (self):
        return self._get_att('db')

    def set_db (self, db):
        return self._set_att('db', db)

    def get_config (self):
        return self.get_db().get_config()

    def get_name (self):
        return self._get_att('name')

    def set_name (self, name):
        return self._set_att('name', name)

    def get_store_id (self):
        return self.get_name()

    def get_folders (self):
        return self.folders

    def get_folder (self, name):
        if name in self.folders:
            return self.folders[name]
        else:
            return None

    def add_folder (self, f):
        self.folders.update({f.get_name() : f})

    def set_folders (self, fs):
        """fs has to be a dictionary"""

        self.folders = fs

    ##
    ## The Real Action
    ##

    def get_con_re (self):
        return self._get_att('con_re')

    def set_con_re (self, reg):
        return self._set_att('con_re', reg)

    def get_str_re (self):
        return self._get_att('str_re')

    def set_str_re (self, reg):
        return self._set_att('str_re', reg)

    def get_adr_re (self):
        return self._get_att('adr_re')

    def set_adr_re (self, reg):
        return self._set_att('adr_re', reg)

    def get_ph_re (self):
        return self._get_att('ph_re')

    def set_ph_re (self, reg):
        return self._set_att('ph_re', reg)

    def get_note_re (self):
        return self._get_att('note_re')

    def set_note_re (self, reg):
        return self._set_att('note_re', reg)

    def get_notes_re (self):
        return self._get_att('notes_re')

    def set_notes_re (self, reg):
        return self._set_att('notes_re', reg)

    def get_sync_tag_re (self):
        return self._get_att('sync_tag_re')

    def set_sync_tag_re (self, reg):
        return self._set_att('sync_tag_re', reg)

    @classmethod
    def get_def_folder_name (self):
        return 'default'

    def _set_regexes (self):
        res = {'string' : r'"[^"\\]*(?:\\.[^"\\]*)*"|nil',
               'ws'     : '\s*'}
        re_str_ar = 'nil|\(((' + res['string'] + ')' + res['ws'] + ')*\)'
        res.update({'string_array' : re_str_ar})

        ## Phones
        re_ph_vec = ('\[\s*((?P<phlabel>' + res['string'] + 
                     ')\s*(?P<number>(?P<unstructured>'  +
                     res['string'] + ')|'+
                     '(?P<structured>\d+\s+\d+\s+\d+\s+\d+)' +
                     '\s*))\]')
        re_phs = 'nil|(\(\s*(' + re_ph_vec + '\s*)+)\)'
        res.update({'ph_vec' : re_phs})

        ## Addresses
        re_ad_vec = ('\[\s*(?P<adlabel>' + res['string'] + ')\s*(' +
                     '(?P<streets>' + res['string_array'] + ')\s*' +
                     '(?P<city>'    + res['string'] + ')\s*' +
                     '(?P<state>'   + res['string'] + ')\s*' +
                     '(?P<zip>('    + res['string'] + ')|(' + '\d\d\d\d\d))\s*' +
                     '(?P<country>' + res['string'] + ')' +
                     ')\s*\]')
        re_ads = 'nil|\(\s*(' + re_ad_vec + '\s*)+\)'
        res.update({'ad_vec' : re_ads})


        re_note = ('\((?P<field>[^()]+)\s*\.\s*(?P<value>' +
                   res['string'] + '|\d+)+\)')
        re_notes = '\((' + re_note + '\s*)+\)'
        res.update({'note'  : re_note})
        res.update({'notes' : re_notes})

        ## A full contact entry
        re_con = ('\[\s*' +
                  '(?P<firstname>' + res['string']       + ')\s*' +
                  '(?P<lastname>'  + res['string']       + ')\s*' +
                  '(?P<affix>'     + res['string_array'] + ')\s*' +
                  '(?P<aka>'       + res['string_array'] + ')\s*' +
                  '(?P<company>'   + res['string_array'] + ')\s*' +
                  '(?P<phones>'    + res['ph_vec']       + ')\s*' +
                  '(?P<addrs>'     + res['ad_vec']       + ')\s*' +
                  '(?P<emails>'    + res['string_array'] + ')\s*' +
                  '(?P<notes>'     + res['notes']        + ')\s*' +
                  '(?P<cache>'     + res['string']       + ')\s*' +
                  '\s*\]')

        ## Now save some of the regexes for later use...
        self.set_con_re(re_con)
        self.set_str_re(res['string'])
        self.set_adr_re(re_ad_vec)
        self.set_ph_re(re_ph_vec)
        self.set_note_re(res['note'])
        self.set_notes_re(res['notes'])

        # Compute and store away a regular expression to match sync tags in
        # the notes section
        c = self.get_config()
        p = c.get_label_prefix()
        s = c.get_label_separator()
        r = '%s%s\w+%s' % (p, s, s)
        self.set_sync_tag_re(r)

    def set_file_format (self, ver):
        return self._set_att('file_format', ver)

    def get_file_format (self):
        return self._get_att('file_format')

    def populate_folders (self, fn=None):
        """Parse a BBDB file contents, and create folders of contacts."""

        ## BBDB itself is not structured as logical folders. The concept of a
        ## BBDB folder is overlayed by ASynK. Any contact with a notes field
        ## with key called 'folder' (or as configured in config.json), is
        ## assigned to a folder of that name. If an object does not have a
        ## folder note, it is assgined to the default folder.

        ## This routine parses the BBDB file by reading one line at at time
        ## from top to bottom. Due to a limitation in how the Contact() and
        ## Folder() classes interact, we have to pass a valid Folder object to
        ## the Contact() constructor. So the way we do this is we start by
        ## assuming the contact is in the default folder. After successful
        ## parsing, if the folder name is available in the contact, we will
        ## move it from the dfault folder to that particular folder.

        if not fn:
            fn = self.get_name()

        logging.info('Parsing BBDB file %s...', fn)

        def_fn = self.get_def_folder_name()
        def_f = BBContactsFolder(self.get_db(), def_fn, self)
        self.add_folder(def_f)

        with codecs.open(fn, encoding='utf-8') as bbf:
            ff = bbf.readline()
            if re.search('coding:', ff):
                # Ignore first line if it is: ;; -*-coding: utf-8-emacs;-*-
                ff = bbf.readline()

            # Processing: ;;; file-format: 8
            res = re.search(';;; file-(format|version):\s*(\d+)', ff)
            if not res:
                bbf.close()
                raise BBDBFileFormatError('Unrecognizable format line: %s' % ff)

            ver = int(res.group(2))
            self.set_file_format(ver)

            if ver < 7:
                bbf.close()
                raise BBDBFileFormatError(('Need minimum file format ver 7. ' +
                                          '. File version is: %d' ) % ver)

            cnt = 0
            while True:
                ff = bbf.readline()
                if ff == '':
                    break

                if re.search('^;', ff):
                    continue

                c  = BBContact(def_f, rec=ff.rstrip())
                fn = c.get_bbdb_folder()

                if fn:
                    f = self.get_folder(fn)
                    if not f:
                        f = BBContactsFolder(self.get_db(), fn, self)
                        self.add_folder(f)
                    f.add_contact(c)
                else:
                    def_f.add_contact(c)

                # self.add_contact(c)

                cnt += 1

        logging.info('Successfully parsed %d entries.', cnt)
        bbf.close()

    def save_file (self, fn=None):
        if not fn:
            fn = self.get_name() + '.out'

        logging.info('Saving BBDB File %s: %s...', self.get_name(), fn)

        with codecs.open(fn, 'w', encoding='utf-8') as bbf:
            bbf.write(';; -*-coding: utf-8-emacs;-*-\n')
            bbf.write(';;; file-format: 7\n')

            for bbdbid, bbc in self.get_contacts().iteritems():
                con = bbc.init_rec_from_props()
                bbf.write('%s\n' % unicode(con))

        bbf.close()
        self.set_clean()

class BBPIMDB(PIMDB):
    """Wrapper class over the BBDB, by implementing the PIMDB abstract
    class."""

    def __init__ (self, config, def_fn):
        PIMDB.__init__(self, config)

        self.set_msgstores({})

        def_ms = self.add_msgstore(def_fn)
        self.set_def_msgstore(def_ms)

        self.set_folders()

    ##
    ## First implementation of the abstract methods of PIMDB.
    ##

    def get_dbid (self):
        """See the documentation in class PIMDB"""

        return 'bb'

    def get_msgstores (self):
        return self.msgstores

    def set_msgstores (self, ms):
        self.msgstores = ms
        return ms

    def get_def_msgstore (self):
        return self.def_msgstore

    def set_def_msgstore (self, ms):
        self.def_msgstore = ms
        return ms

    def add_msgstore (self, ms):
        """Add another messagestore to the PIMDB. ms can be either a string,
        or an object of type MessageStore. If it is a string, then the string
        is interpreted as the fully expanded name of a BBDB file, and it is
        parsed accordingly. If it is an object already, then it is simply
        appended to the existing list of stores."""

        if isinstance(ms, MessageStore):
            self.msgstores.update({ms.get_name(): ms})
        elif isinstance(ms, basestring):
            ms = MessageStore(self, ms)
            self.msgstores.update({ms.get_name() : ms})
        else:
            logging.error('Unknown type (%s) in argument to add_msgstore %s',
                          type(ms), ms)
            return None

        return ms

    def new_folder (self, fname, ftype=None, storeid=None):
        """See the documentation in class PIMDB.

        fname should be a filename in this case.
        """

        with codes.open(fname, 'w', encoding='utf-8') as bbf:
            bbf.write(';; -*-coding: utf-8-emacs;-*-\n')
            bbf.write(';;; file-format: 7\n')
            bbf.close()

        logging.info('Successfully Created BBDB file: %s', fname)
        f = BBContactsFolder(self, fname)
        if f:
            self.add_contacts_folder(f)

    def show_folder (self, gid):
        logging.info('%s: Not Implemented', 'pimd_bb:show_folder()')

    def del_folder (self, gid):
        """See the documentation in class PIMDB"""

        raise NotImplementedError

    def set_folders (self):
        """See the documentation in class PIMDB"""

        for name, store in self.get_msgstores().iteritems():
            for name, f in store.get_folders().iteritems():
                self.add_to_folders(f)

    def set_def_folders (self):
        """See the documentation in class PIMDB"""

        def_store  = self.get_def_msgstore()
        def_folder = def_store.get_folder(MessageStore.get_def_folder_name())
        self.set_def_folder(Folder.CONTACT_t, def_folder)

    def set_sync_folders (self):
        """See the documentation in class PIMDB"""

        raise NotImplementedError

    def prep_for_sync (self, dbid):
        pass
      
    ##
    ## Now the non-abstract methods and internal methods
    ##

    @classmethod
    def get_bbdb_time (self, t=None):
       """Convert a datetime.datetime object to a time string formatted in the
       bbdb-time-stamp-format of version 7 file format. BBDB timestamps are
       always represented in UTC. So the passed value should either be a naive
       object having the UTC time, or an aware object with tzinfo set."""
    
       # The bbbd ver 7 format uses time stamps in the following format:
       # "%Y-%m-%d %T %z", for e.g. 2012-04-17 09:49:16 +0000. The following
       # code converts a specified time instance (seconds since epoch) to the
       # right format
    
       if not t:
           t = datetime.datetime.utcnow()
       else:
           if t.tzinfo:
               t = t - t.tzinfo.utcoffset(t)
    
       return t.strftime('%Y-%m-%d %H:%M:%S +0000', )

    @classmethod
    def parse_bbdb_time (self, t):
        """Return a datetime object containing naive UTC timestamp based on
        the specified BBDB timestamp string."""

       # IMP: Note that we assume the time is in UTC - and ignore what is
       # actually in the string. This sucks, but this is all I am willing to
       # do for the m moment. FIXME

        res = re.search(r'(\d\d\d\d\-\d\d\-\d\d \d\d:\d\d:\d\d).*', t)
        if res:
            t = res.group(1)
        else:
            return None
        
        return datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S')
