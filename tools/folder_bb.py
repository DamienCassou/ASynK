##
## Created       : Sat Apr 07 20:03:04 IST 2012
## Last Modified : Sun Apr 08 22:24:07 IST 2012
##
## Copyright (C) 2012 Sriram Karra <karra.etc@gmail.com>
##
## Licensed under the GPL v3
## 

import logging, re
from   folder     import Folder
from   contact_bb import BBContact

class BBDBFileFormatError(Exception):
    pass

class BBContactsFolder(Folder):
    
    def __init__ (self, db, fn):
        Folder.__init__(self, db)
        self.set_name(fn)

        self.contacts = {}
        self.read_contacts()

        self.write_contacts()

    ##
    ## Implementation of the abstract methods inherited from Folder
    ##

    def get_batch_size (self):
        return 1000

    def prep_sync_lists (self, destid, sl, updated_min=None, cnt=0):
        raise NotImplementedError

    def find_item (self, itemid):
        raise NotImplementedError

    def find_items (self, itemids):
        raise NotImplementedError

    def batch_create (self, src_sl, src_dbid, items):
        raise NotImplementedError

    def batch_update (self, sync_list, src_dbid, items):
        raise NotImplementedError

    def writeback_sync_tags (self, items):
        raise NotImplementedError

    def bulk_clear_sync_flags (self, dbids):
        raise NotImplementedError

    def __str__ (self):
        ret = 'Contacts'

        return ('%s.\tName: %s;\tGID: %s;\t' % (ret, self.get_name(),
                                                self.get_itemid()))

    ##
    ## Internal and helper routines
    ##

    def add_contact (self, itemid, bbc):
        self.contacts.update({itemid : bbc})

    def get_contacts (self):
        return self.contacts

    def read_contacts (self, fn=None):
        if not fn:
            fn = self.get_name()

        with open(fn) as bbf:
            bbf.readline()
            # Ignore first line which is: ;; -*-coding: utf-8-emacs;-*-

            ff = bbf.readline()
            # Processing: ;;; file-format: 8

            res = re.search(';;; file-(format|version):\s*(\d+)', ff)
            if not res:
                bbf.close()
                raise BBDBFileFormatError('Unrecognizable format line: %s' % ff)

            ver = int(res.group(2))
            if ver < 7:
                bbf.close()
                raise BBDBFileFormatError(('Need minimum file format ver 7. ' +
                                          '. File version is: %d' ) % ver)

            bbf.readline()
            # Ignore the user-fields line. What's the point of that anyway...

            while True:
                ff = bbf.readline()
                if ff == '':
                    break

                c = BBContact(self, rec=ff.rstrip())
                self.add_contact(c.get_itemid(), c)
                logging.debug('Successfully read and processed: %s',
                              c.get_name())
                #str(c))

        bbf.close()

    def write_contacts (self, fn=None):
        if not fn:
            fn = self.get_name() + '.out'

        with open(fn, 'w') as bbf:
            bbf.write(';; -*-coding: utf-8-emacs;-*-\n')
            bbf.write(';;; file-format: 8\n')
            bbf.write(';;; user-fields: (%s)\n' %
                      self.get_user_fields_as_string())

            for bbdbid, bbc in self.get_contacts().iteritems():
                con = bbc.init_rec_from_props()
                bbf.write('%s\n' % con)

        bbf.close()

    def get_user_fields_as_string (self):
        # FIXME: Do something meanginful with this
        return 'mail-alias'
