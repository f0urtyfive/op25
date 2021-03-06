#!/usr/bin/env python

# Copyright 2008-2011 Steve Glass
# 
# Copyright 2011, 2012, 2013, 2014, 2015, 2016, 2017 Max H. Parke KA1RBI
# 
# This file is part of OP25
# 
# OP25 is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# OP25 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
# License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with OP25; see the file COPYING. If not, write to the Free
# Software Foundation, Inc., 51 Franklin Street, Boston, MA
# 02110-1301, USA.

import sys
import curses
import curses.textpad
import time
import json
import threading
import traceback

from gnuradio import gr

class curses_terminal(threading.Thread):
    def __init__(self, input_q,  output_q, **kwds):
        threading.Thread.__init__ (self, **kwds)
        self.setDaemon(1)
        self.input_q = input_q
        self.output_q = output_q
        self.keep_running = True
        self.last_update = 0
        self.auto_update = True
        self.current_nac = None
        self.start()

    def setup_curses(self):
        self.stdscr = curses.initscr()

        curses.noecho()
        curses.halfdelay(1)

        self.top_bar = curses.newwin(1, 80, 0, 0)
        self.freq_list = curses.newwin(20, 80, 1, 0)
        self.active1 = curses.newwin(1, 80, 21, 0)
        self.active2 = curses.newwin(1, 80, 22, 0)
        self.prompt = curses.newwin(1, 10, 23, 0)
        self.text_win = curses.newwin(1, 70, 23, 10)

        self.textpad = curses.textpad.Textbox(self.text_win)

    def end_curses(self):
        try:
            curses.endwin()
        except:
            pass

    def do_auto_update(self):
        UPDATE_INTERVAL = 1	# sec.
        if not self.auto_update:
            return False
        if self.last_update + UPDATE_INTERVAL > time.time():
            return False
        self.last_update = time.time()
        return True

    def process_terminal_events(self):
        # return true signifies end of main event loop
        _ORD_S = ord('s')
        _ORD_L = ord('l')
        _ORD_H = ord('h')
        COMMANDS = {_ORD_S: 'skip', _ORD_L: 'lockout', _ORD_H: 'hold'}
        c = self.stdscr.getch()
        if c == ord('u') or self.do_auto_update():
            msg = gr.message().make_from_string('update', -2, 0, 0)
            self.output_q.insert_tail(msg)
        if c in COMMANDS.keys():
            msg = gr.message().make_from_string(COMMANDS[c], -2, 0, 0)
            self.output_q.insert_tail(msg)
        elif c == ord('q'):
		return True
        elif c == ord('t'):
            if self.current_nac:
                msg = gr.message().make_from_string('add_default_config', -2, int(self.current_nac), 0)
                self.output_q.insert_tail(msg)
        elif c == ord('f'):
            self.prompt.addstr(0, 0, 'Frequency')
            self.prompt.refresh()
            self.text_win.clear()
            response = self.textpad.edit()
            self.prompt.clear()
            self.prompt.refresh()
            self.text_win.clear()
            self.text_win.refresh()
            try:
                freq = float(response)
                if freq < 10000:
                    freq *= 1000000.0
            except:
                freq = None
            if freq:
                msg = gr.message().make_from_string('set_freq', -2, freq, 0)
                self.output_q.insert_tail(msg)
        elif c == ord('x'):
            assert 1 == 0
        return False

    def process_json(self, js):
        # return true signifies end of main event loop
        msg = json.loads(js)
        if msg['json_type'] == 'trunk_update':
            nacs = [x for x in msg.keys() if x != 'json_type']
            if not nacs:
                return
            times = {msg[nac]['last_tsbk']:nac for nac in nacs}
            current_nac = times[ sorted(times.keys(), reverse=True)[0] ]
            self.current_nac = current_nac
            s = 'NAC 0x%x' % (int(current_nac))
            s += ' WACN 0x%x' % (msg[current_nac]['wacn'])
            s += ' SYSID 0x%x' % (msg[current_nac]['sysid'])
            s += ' %f' % (msg[current_nac]['rxchan']/ 1000000.0)
            s += '/%f' % (msg[current_nac]['txchan']/ 1000000.0)
            s += ' tsbks %d' % (msg[current_nac]['tsbks'])
            freqs = sorted(msg[current_nac]['frequencies'].keys())
            s = s[:79]
            self.top_bar.clear()
            self.top_bar.addstr(0, 0, s)
            self.top_bar.refresh()
            self.freq_list.clear()
            for i in xrange(len(freqs)):
                s=msg[current_nac]['frequencies'][freqs[i]]
                s = s[:79]
                self.freq_list.addstr(i, 0, s)
            self.freq_list.refresh()
            self.stdscr.refresh()
        elif msg['json_type'] == 'change_freq':
            s = 'Frequency %f' % (msg['freq'] / 1000000.0)
            if msg['tgid'] is not None:
                s += ' Talkgroup ID %s' % (msg['tgid'])
                if msg['tdma'] is not None:
                    s += ' TDMA Slot %s' % msg['tdma']
            self.active1.clear()
            self.active2.clear()
            self.active1.addstr(0, 0, s)
            self.active1.refresh()
            if msg['tag']:
                s = msg['tag']
                s = s[:79]
                self.active2.addstr(0, 0, s)
            self.active2.refresh()
            self.stdscr.refresh()
        return False

    def process_q_events(self):
        # return true signifies end of main event loop
        while True:
            if self.input_q.empty_p():
                break
            msg = self.input_q.delete_head_nowait()
            if msg.type() == -4:
                return self.process_json(msg.to_string())
        return False

    def run(self):
        try:
            self.setup_curses()
            while(self.keep_running):
                if self.process_terminal_events():
                    break
                if self.process_q_events():
                    break
        except:
            sys.stderr.write('terminal: exception occurred\n')
            sys.stderr.write('terminal: exception:\n%s\n' % traceback.format_exc())
        finally:
            self.end_curses()
        msg = gr.message().make_from_string('quit', -2, 0, 0)
        self.output_q.insert_tail(msg)
