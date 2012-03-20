##
## Created       : Thu Jul 07 14:47:54 IST 2011
## Last Modified : Tue Mar 20 16:39:36 IST 2012
## 
## Copyright (C) 2011, 2012 by Sriram Karra <karra.etc@gmail.com>
## 
## Licensed under the GPL v3
## 

## This file itself comes with some extensive unit tests. If you want to run
## it from the command line, the usage is (from the current directory)
## PYTHONPATH=../lib/:. python pimdb_gc.py

import sys, getopt, logging, xml.dom.minidom
import utils, time, datetime
import atom, gdata.contacts.data, gdata.contacts.client, base64

from   state        import Config
from   pimdb        import PIMDB, GoutInvalidPropValueError
from   folder       import Folder
from   folder_gc    import GCContactsFolder

def get_udp_by_key (udps, key):
    
    for ep in udps:
        if ep.key == key:   
            if ep.value:
                return ep.value
            else:
                value = 'Hrrmph. '
                print 'Value: ', value

    return None

class GCPIMDB (PIMDB):
    """GC object is a wrapper for a Google Contacts stream API."""

    def __init__(self, config, user, pw):
        PIMDB.__init__(self, config)
        self.set_user(user)
        self.set_pw(pw)
        self.gc_init()

        self.set_folders()

    ##
    ## First implementation of the abstract methods of PIMDB.
    ##

    def get_dbid (self):
        """See the documentation in class PIMDB"""

        return 'gc'

    def new_folder (self, fname, type):
        if type != Folder.CONTACT_t:
            logging.erorr('Only Contact Groups are supported at this time.')
            return None

        gn              = gdata.data.Name(name=fname)
        new_group       = gdata.contacts.data.GroupEntry(name=gn)
        new_group.title = atom.data.Title(text=fname)
    
        entry = self.get_gdc().create_group(new_group)
    
        if entry:
            logging.info('Successfully created group. ID: %s',
                         entry.id.text)
            f = GCContactsFolder(self, entry.id.text, gn, entry)
            self.add_contacts_folder(f)
            return entry.id.text
        else:
            logging.error('Could not create Group \'%s\'', gn)
            return None

    def del_folder (self, gid):
        f, ftype = self.find_folder(gid)

        if not f:
            logging.error('Group ID not found in folder list: %s', gid)
            return

        logging.info('Deleting Entries for Group: %s...', f.get_name())
        f.del_all_entries()
        logging.info('Deleting Entries for Group: %s...done', f.get_name())

        logging.info('Deleting the Group from Google''s servers...')
        self.get_gdc().delete_group(f.get_gcentry())
        logging.info('Deleting the Group from Google''s servers...done')

        self.remove_folder_from_lists(f, ftype)

    def set_folders (self):
        """See the documentation in class PIMDB"""

        logging.debug('Getting Group List to populate folders...')
        groups = self.list_groups()
        for (gid, gn, gcentry) in groups:
            f = GCContactsFolder(self, gid, gn, gcentry)
            self.add_contacts_folder(f)

    def set_def_folders (self):
        """See the documentation in class PIMDB"""

        raise NotImplementedError
   
    def set_sync_folders (self):
        """See the documentation in class PIMDB"""

        raise NotImplementedError

    ##
    ## Now the non-abstract methods and internal methods
    ## 

    def get_user (self):
        return self.user

    def set_user (self, user):
        self.user = user

    def get_pw (self):
        return self.pw

    def set_pw (self, pw):
        self.pw = pw

    def get_gdc (self):
        return self.gdc

    def set_gdc (self, gdc):
        self.gdc = gdc

    def gc_init (self):
        logging.debug('Logging into Google...')

        gdc = gdata.contacts.client.ContactsClient(source='Gout-Sync')
        gdc.ClientLogin(self.get_user(), self.get_pw(), gdc.source)
        self.set_gdc(gdc)

        # if not self.get_config().get_gid():
        #     logging.info('First use of application. Creating group...')
        #     gn = self.config.get_gn()
        #     if not gn:
        #         gn = 'Gout'
        #         self.config.set_gn(gn, False)
        #         logging.info('Using default Gmail Contacts Group: Gout')

        #     gc_gid = self.create_group(gn)
        #     self.config.set_gid(gc_gid)


    def get_groups_feed (self):
        feed = self.get_gdc().GetGroups()
        return feed

    def list_groups (self):
        ret = []
        feed = self.get_groups_feed()
  
        if not feed.entry:
            return ret

        for i, entry in enumerate(feed.entry):
            name = entry.content.text if entry.content else entry.title.text
            ret.append((entry.id.text, name, entry))

        return ret

    def print_groups (self):
        feed = self.get_groups_feed()
  
        if not feed.entry:
            print 'No groups for user'
        for i, entry in enumerate(feed.entry):
            print '\n%s %s' % (i+1, entry.title.text)
            if entry.content:
                print '  Content: %s' % (entry.content.text)

            print '  Group ID: %s' % entry.id.text  

    def find_group (self, title, ret_type='id'):
        """This routine will directly look up the server using the API and try
        to find the specified group by name.
  
        Takes a group title, and returns the Group ID if found. Returns
        None if the group cannot be found.
        """
  
        feed = self.get_gdc().GetGroups()
    
        if not feed.entry:
            logging.info('\nGroup (%s) not found: there are no groups!',
                          title)
            return None
    
        for i, entry in enumerate(feed.entry):
            if entry.title.text == title:
                if ret_type == 'entry':
                    return entry
                else:
                    return entry.id.text

        return None

    def new_feed (self):
        return gdata.contacts.data.ContactsFeed()

    def exec_batch (self, batch_feed):
        return self.get_gdc().ExecuteBatch(
            batch_feed, gdata.contacts.client.DEFAULT_BATCH_URL)


def main():
    config = Config('../app_state.json')
    
    # Parse command line options
    try:
        opts, args = getopt.getopt(sys.argv[1:], '', ['user=', 'pw='])
    except getopt.error, msg:
        print 'python gc_wrapper.py --user [username] --pw [password]'
        sys.exit(2)
  
    user = ''
    pw = ''
    # Process options
    for option, arg in opts:
        if option == '--user':
            user = arg
        elif option == '--pw':
            pw = arg
  
    try:
        sample = GCPIMDB(config, user, pw)
    except gdata.client.BadAuthentication:
        print 'Invalid credentials. WTF.'
        return
  
    sample.print_groups()
    gid = sample.new_folder('Hurrah Testing', Folder.CONTACT_t)
    #gid = 'http://www.google.com/m8/feeds/groups/karra.etc%40gmail.com/base/50fccc2a8e0100eb'
    sample.del_folder(gid)
    sample.print_groups()

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    main()
