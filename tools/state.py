#!/usr/bin/env python

## Created	 : Tue Jul 19 13:54:53  2011
## Last Modified : Thu Aug 25 13:21:51  2011
##
## Copyright 2011 Sriram Karra <karra.etc@gmail.com>
##
## Licensed under the GPL v3
## 

import demjson
import logging

class Config:

    OUTLOOK = 1
    GOOGLE  = 2

    # There has to be a better way than this...
    sync_strs = [None, 'OUTLOOK', 'GOOGLE']

    def __init__ (self, fn):
        fi = None
        self.fn = fn
        try:
            fi = open(fn, "r")
        except IOError, e:
            logging.critical('Error! Could not Open file (%s): %s', fn, e)
            return

        st = fi.read()
        self.inp = demjson.decode(st)

        self.state = self.inp
        self.state['conflict_resolve'] = getattr(
            self, self.inp['conflict_resolve'])


    def _get_prop (self, key):
        return self.state[key]

    def _set_prop (self, key, val):
        self.state[key] = val

    def get_gc_guid (self):
        return self._get_prop('GC_GUID')

    def get_gc_id (self):
        return self._get_prop('GC_ID')

    def get_gid (self):
        return self._get_prop('gid')

    def get_cr (self):
        return self._get_prop('conflict_resolve')

    def get_gn (self):
        return self._get_prop('gn')

    def get_last_sync_start (self):
        return self._get_prop('last_sync_start')

    def get_last_sync_stop (self):
        return self._get_prop('last_sync_stop')

    def get_resolve (self):
        return self._get_prop('conflict_resolve')

    def set_resolve (self, val):
        return self._set_prop('conflict_resolve', val)

    def save (self, fn):
        if not fn:
            fn = self.fn

        try:
            fi = open(fn, "w")
        except IOError, e:
            logging.critical('Error! Could not Open file (%s): %s', fn, e)
            return

        save = self.get_resolve()
        if save:
            self.set_resolve(self.sync_strs[save])

        fi.write(demjson.encode(self.state))

        if save:
            self.set_resolve(save)

        fi.close()
