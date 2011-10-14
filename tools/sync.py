#!/usr/bin/env python

## Created	 : Tue Jul 19 15:04:46  2011
## Last Modified : Thu Oct 13 19:24:07 IST 2011
##
## Copyright 2011 Sriram Karra <karra.etc@gmail.com>
##
## Licensed under the GPL v3
## 

from   state         import Config
from   ol_wrapper    import Outlook, Contact
from   gc_wrapper    import GC
from   win32com.mapi import mapitags, mapiutil

import utils
import gdata.contacts.client
import atom

import demjson
import logging
import base64
import xml.dom.minidom

def sync_status_str (const):
    for name, val in globals().iteritems():
        if name[:5] == 'SYNC_' and val == const:
            return name

    return None

SYNC_OK                    = 200
SYNC_CREATED               = 201
SYNC_NOT_MODIFIED          = 304
SYNC_BAD_REQUEST           = 400
SYNC_UNAUTHORIZED          = 401
SYNC_FORBIDDEN             = 403
SYNC_CONFLICT              = 409
SYNC_INTERNAL_SERVER_ERROR = 500

class Sync:
    def __init__ (self, config, fields, ol, gc):
        self.config = config
        self.fields = fields
        self.ol     = ol
        self.gc     = gc


    def reset_state (self):
        """Reset counters and other state information before starting."""
        pass


    def _prep_lists (self):
        """Identify the list of contacts that need to be copied from one
        place to the other and set the stage for the actual sync"""

        self.gc.prep_gc_contact_lists()
        self.ol.prep_ol_contact_lists()

        # Identify potential conflicts in the modified lists and resolve
        # them by deleting the conflict entries from one of the two
        # lists

        old = self.ol.con_mod
        gcd = self.gc.con_gc_mod

        coma = [ol for ol,gc in old.iteritems() if gc in gcd.keys()]

        logging.info('# Conflicts found (modified both places): %d',
                     len(coma) if coma else 0)

        cr = self.config.get_resolve()
        if cr == self.config.OUTLOOK:
            # The olids in google contacts side are all base64
            # encoded. Ensure we send an encoded array as well
            coma = [base64.b64encode(x) for x in coma]
            self.gc.del_con_mod_by_values(coma)
        elif cr == self.config.GOOGLE:
            self.ol.del_con_mod_by_keys(coma)

        print 'cr : ', cr
        print 'size of gc mod: ', len(self.gc.con_gc_mod)
        print 'size of ol mod: ', len(self.ol.con_mod)

    class BatchState:
        def __init__ (self, num, f, op=None):
            self.size = 0
            self.cnt  = 0
            self.num  = num
            self.f    = f
            self.operation = op
            self.cons = {}      # can be either Contact or ContactEntry

        def get_size (self):
            """Return size of feed in kilobytess."""
            self.size = len(str(self.f))/1024.0
            return self.size

        def incr_cnt (self):
            self.cnt += 1
            return self.cnt

        def get_cnt (self):
            return self.cnt

        def get_bnum (self):
            return self.num

        def add_con (self, olid_b64, con):
            self.cons[olid_b64] = con

        def get_con (self, olid_b64):
            return self.cons[olid_b64]

        def get_operation (self):
            return self.operation

        def set_operation (self, op):
            self.operation = op

    def process_batch_response (self, resp, bstate):
        """resp is the response feed obtained from a batch operation to
        google.

        bstate contains the stats and other state for all the Contact
        objects involved in the batch operation.

        This routine will walk through the batch response entries, and
        make note in the outlook database for succesful sync, or handle
        errors appropriately."""

        op   = bstate.get_operation()
        cons = []

        for entry in resp.entry:
            bid    = entry.batch_id.text if entry.batch_id else None
            code   = int(entry.batch_status.code)
            reason = entry.batch_status.reason

            if code != SYNC_OK and code != SYNC_CREATED:
                # FIXME this code path needs to be tested properly
                err = sync_status_str(code)
                err_str = '' if err is None else ('Code: %s' % err)
                err_str = 'Reason: %s. %s' % (reason, err_str)

                logging.error('Sync failed for bid %s: %s',
                              bid, err_str)
            else:
                if op == 'query':
                    con = entry
                    # We could build and return array for all cases, but
                    # why waste memory...
                    cons.append(con)
                else:
                    con  = bstate.get_con(bid)
                    gcid = utils.get_link_rel(entry.link, 'edit')
                    con.update_prop_by_name([(self.config.get_gc_guid(),
                                              self.config.get_gc_id())],
                                            mapitags.PT_UNICODE,
                                            gcid)

        return cons

    def _send_new_ol_to_gc (self):
        f = self.gc.new_feed()
        stats = Sync.BatchState(1, f, 'insert')

        for olid in self.ol.get_con_new():
            c  = Contact(fields=self.fields, config=self.config,
                         ol=self.ol, entryid=olid, props=None,
                         gcapi=self.gc)
            ce = c.get_gc_entry()
            bid = base64.b64encode(c.entryid)
            stats.add_con(bid, c)

            f.add_insert(entry=ce, batch_id_string=bid)
            stats.incr_cnt()

            if stats.get_cnt() % 10 == 0:
                # Feeds have to be less than 1MB. We can push this some
                # more. FIXME. Atleast 200
                logging.info('Uploading new batch # %02d to Google. Count: %3d. Size: %6.2fK',
                             stats.get_bnum(), stats.get_cnt(),
                             stats.get_size())
                rf = self.gc.exec_batch(f)
                self.process_batch_response(rf, stats)

                f = self.gc.new_feed()
                s = Sync.BatchState(stats.get_bnum()+1, f, 'insert')
                stats = s

                break           # debug

        # Upload any leftovers
        if stats.get_cnt() > 0:
            logging.info('New Batch # %02d. Count: %3d. Size: %5.2fK',
                         stats.get_bnum(), stats.get_cnt(),
                         stats.get_size())
            rf = self.gc.exec_batch(f)
            self.process_batch_response(rf, stats)


    def _fetch_gc_entries (self, gcids):
        """gcids is a list of google contact ids to retrieve contact
        entries for.

        Returns a list of ContactEntries"""

        logging.info('Querying Google for status of Contact Entries')

        gid    = self.config.get_gid()
        f      = self.gc.new_feed()
        stats = Sync.BatchState(1, f, 'query')

        ret = []

        for gcid in gcids:
            ce = gdata.contacts.data.ContactEntry()
            ce.id = atom.data.Id(text=gcid)
            stats.add_con(gcid, ce)

            f.add_query(entry=ce, batch_id_string=gcid)
            stats.incr_cnt()

            if stats.get_cnt() % 200 == 0:
                # Feeds have to be less than 1MB. We can push this some
                # more
                logging.info('Qry Batch # %02d. Count: %3d. Size: %6.2fK',
                             stats.get_bnum(), stats.get_cnt(),
                             stats.get_size())

                rf  = self.gc.exec_batch(f)
                ces = self.process_batch_response(rf, stats)
                [ret.append(x) for x in ces]

                f = self.gc.new_feed()
                s = Sync.BatchState(stats.get_bnum()+1, f, 'query')
                stats = s

        # Process any leftovers
        if stats.get_cnt() > 0:
            logging.info('Qry Batch # %02d. Count: %3d. Size: %5.2fK',
                         stats.get_bnum(), stats.get_cnt(),
                         stats.get_size())
            
            rf  = self.gc.exec_batch(f)
            ces = self.process_batch_response(rf, stats)
            [ret.append(x) for x in ces]

        logging.info('Response recieved from Google. Processing...')
        return ret

    def _send_mod_ol_to_gc (self):
        f = self.gc.new_feed()
        stats = Sync.BatchState(1, f, 'update')

        # Updates and deletes on google require not just the entryid but
        # also its correct etag which is a version identifier. This is
        # to ensure two apps do not overwrite each other's work without
        # even knowing about it. So we need to approach this in two
        # steps: (a) Fetch the ContactEntries for all the items we are
        # interested in. the returned entry objects have all the
        # required info, including the latest etag. (b) Modify the same
        # entry with the local updates and send it back
        #
        # Note that we are already performing one query to Google
        # already while prepping the lists. However that step will not
        # retrieve entries for local modifications. There is some
        # potential for bandwidth optimisation here, however it would
        # be very premature to d o that at this time.

        ces = self._fetch_gc_entries(self.ol.get_con_mod().values())
        if ces and len(ces)>0:
            print 'Num entries obtained: ', len(ces)
        else:
            print 'Got nothing of value'

        for ce in ces:
            c  = Contact(fields=self.fields, config=self.config,
                         ol=self.ol, entryid=None, props=None,
                         gcapi=self.gc, gcentry=ce, data_from_ol=True)
            bid = base64.b64encode(c.entryid)
            stats.add_con(bid, c)
 
            f.add_update(entry=c.get_gc_entry(), batch_id_string=bid)
            stats.incr_cnt()
 
            if stats.get_cnt() % 10 == 0:
                # Feeds have to be less than 1MB. We can push this some
                # more
                logging.info('Mod Batch # %02d. Count: %3d. Size: %6.2fK',
                             stats.get_bnum(), stats.get_cnt(),
                             stats.get_size())
 
                rf = self.gc.exec_batch(f)
                self.process_batch_response(rf, stats)
 
                f = self.gc.new_feed()
                s = Sync.BatchState(stats.get_bnum()+1, f, 'update')
                stats = s
 
        # Upload any leftovers
        if stats.get_cnt() > 0:
            logging.info('Mod Batch # %02d. Count: %3d. Size: %5.2fK',
                         stats.get_bnum(), stats.get_cnt(),
                         stats.get_size())
            rf = self.gc.exec_batch(f)
            self.process_batch_response(rf, stats)


    def _get_new_gc_to_ol (self):
        ces = self._fetch_gc_entries(self.gc.get_con_new())

        f = self.gc.new_feed()
        stats = Sync.BatchState(1, f, 'Writeback olid')

        for ce in ces:
            c  = Contact(fields=self.fields, config=self.config,
                         ol=self.ol, entryid=None, props=None,
                         gcapi=self.gc, gcentry=ce, data_from_ol=False)

            # Save changes in Outlook and write back the olid to the Google
            # Entry

            eid = c.push_to_outlook()
            bid = base64.b64encode(eid)
            stats.add_con(bid, c)

            ce = self.gc.add_olid_to_ce(ce, eid)
            cexml=xml.dom.minidom.parseString('%s'%ce)
            print cexml

            f.add_update(entry=ce, batch_id_string=bid)
            stats.incr_cnt()

            if stats.get_cnt() % 10 == 0:
                logging.info('Uploading state info to Google. ')
                logging.info('Batch #%02d. Count: %3d. Size: %6.2fK',
                             stats.get_bnum(), stats.get_cnt(),
                             stats.get_size())

                rf = self.gc.exec_batch(f)
                self.process_batch_response(rf, stats)
 
                f = self.gc.new_feed()
                s = Sync.BatchState(stats.get_bnum()+1, f, 'Writeback olid')
                stats = s

        # Upload any leftovers
        if stats.get_cnt() > 0:
            logging.info('Uploading state info to Google. ')
            logging.info('Batch # %02d. Count: %3d. Size: %5.2fK',
                         stats.get_bnum(), stats.get_cnt(),
                         stats.get_size())
            rf = self.gc.exec_batch(f)
            self.process_batch_response(rf, stats)


    def _get_mod_gc_to_ol (self):
        """Fetch the entries that we know have been modified on Google side
        and that we want to store in Outlook."""

        f = self.gc.new_feed()
        stats = Sync.BatchState(1, f, 'update')

        logging.info('=====================================================')
        logging.info('   Fetching modified entries from Google Contacts')
        logging.info('=====================================================')
        logging.info('Querying Google for content of modified entries. ')
        logging.info('Expecting to see %d entries...',
                     len(self.gc.get_con_mod().values()))

        ces = self._fetch_gc_entries(self.gc.get_con_mod().values())

        resp = 'Received response from Google. '

        if ces and len(ces)>0:
            resp += '%d entries obtained.' % len(ces)
        else:
            resp += 'No entries found in response.'

        logging.info(resp)

    def _del_ol (self):
        pass

    def _del_gc (self):
        pass

    def _reset_sync (self):
        """Delete all sync related information on Gmail and in Outlook,
        delete the old group and all its contacts, and create a fresh
        group with a new group ID - in sum, make a fresh beginning."""

        self.gc.clear_sync_state()
        self.ol.bulk_clear_gcid_flag()
        self.gc.clear_group(gid=self.config.get_gid(), gentry=None)

        gc_gid = self.gc.create_group(self.config.get_gn())
        self.config.set_gid(gc_gid)

    def run (self):
#        self._reset_sync()
#        self.ol.bulk_clear_gcid_flag()
        self._prep_lists()
#        self._send_new_ol_to_gc()
        self._send_mod_ol_to_gc()
#        self._get_new_gc_to_ol()
#        self._del_gc()
#        self._del_ol()

def main (argv = None):
    print 'Hello World'

if __name__ == "__main__":
    main()
