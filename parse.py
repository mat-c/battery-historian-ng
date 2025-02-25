#!/usr/bin/env python3

# vim: tabstop=4 shiftwidth=4 expandtab

import sys
#for sort
from operator import itemgetter
#for debug
import datetime

#allocate an id starting 0 and incrementing integer
#reuse unsued id
#TODO make priority the smallest number
#today pick a random number in ids_free
class IdAllocator():
    def __init__(self):
        new_id = lambda x: x + 1

        self.ids_in_use = set()
        self.ids_free = set()
        self.new_id = new_id
        self.last_id = 0

    def get_id(self):
        if len(self.ids_free) > 0:
            id = self.ids_free.pop()
        else:
            self.last_id = id = self.new_id(self.last_id)

        self.ids_in_use.add(id)
        return id

    def release_id(self, the_id):
        if the_id in self.ids_in_use:
            self.ids_in_use.remove(the_id)
            self.ids_free.add(the_id)
        else:
            assert(1)

class Time:
    def __init__(self):
        self.time = 0
        self.time_utc = 0

    def add_delta(diff):
        self.time += diff
        self.time_utc += diff

class TraceOutPerfettoJson:
    def __init__(self):
        self.async_ids = IdAllocator()
        self.async_stack = {}
        self.async_max_id = -1

    def simple_event(self, ts, name, start, cat, subname = None):
        if start:
            event='B'
            if subname == None:
                subname = "active"
        else:
            event='E'

        if subname == None:
            print(f"{{\"ph\":\"{event}\", \"ts\": {ts}, \"pid\": \"{cat}\", \"tid\":\"{name}\"}},")
        else:
            print(f"{{\"ph\":\"{event}\", \"ts\": {ts}, \"pid\": \"{cat}\", \"tid\":\"{name}\", \"name\":\"{subname}\"}},")

    def simple_count(self, ts, name, val, cat = "other"):
        event = 'C'
        print(f"{{\"ph\":\"{event}\", \"ts\": {ts}, \"pid\": \"{cat}\", \"name\":\"{name}\", \"args\":{{\"{name}\":\"{val}\"}} }},")

    def simple_event2(self, ts, name, val, cat = "other"):
        event = 'i'
        print(f"{{\"ph\":\"{event}\", \"ts\": {ts}, \"pid\": \"{cat}\", \"tid\":\"{name}\", \"name\":\"{val}\"}},")

    def cat_prio(self, name, prio):
        #XXX this is not supported by perfetto
        event = 'M'
        print(f"{{\"ph\":\"{event}\", \"pid\": \"{name}\", \"name\":\"process_sort_index\", \"args\":{{\"sort_index\":\"{prio}\"}} }},")

class TraceContext:
    def __init__(self, trace_out):
        self.trace_out = trace_out
        self.state_run = False
        self.stop_run_ts = 0
        self.state_wl = False


class EventType:
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        self.long_name = long_name
        self.decode_val_ = decode_val
        self.cat_ = cat
        self.position_ = position
        self.last_ts = 0

    def name(self):
        return self.long_name

    def cat(self):
        return self.cat_

    def position(self):
        return self.position_

    def decode_val(self, val):
        if val != None and self.decode_val_ != None:
            dval = self.decode_val_(val)
        else:
            dval = val
        print(f"decode val {val} {dval}", file=sys.stderr)
        return dval

    def assert_warn(self, cond, trace_ctx, time, msg):
        if False:
            assert(cond)
        elif not cond:
            trace_ctx.trace_out.simple_event2(time, "assert", msg, cat = "errors")

    def ts_check(self, ts):
        print(f"ts {ts} {self.last_ts} {ts - self.last_ts}", file=sys.stderr)
        if ts < self.last_ts:
            print(f"ts back {ts} {self.last_ts} {ts - self.last_ts}", file=sys.stderr)
        assert(ts >= self.last_ts)
        self.last_ts = ts

    def end(self, trace_out, time):
        None

class EventStartStopSingle(EventType):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
        self.is_started = False
        self.last_active = None
    def process(self, trace_ctx, time, start_nstop, val):
        self.assert_warn(trace_ctx.state_run, trace_ctx, time, f"event {self.name()} when not run")
        super().ts_check(time)
        #at trace startup we have initial state without +/-
        if start_nstop == None:
            start_nstop = True

        dval = self.decode_val(val)

        #if not start_nstop and dval is None:
        #    dval = self.last_active

        #stop should match start value
        if not start_nstop:
            assert(val == self.last_active)

        #we should not have 2 start or 2 stop
        assert(self.is_started != start_nstop)

        #some trace have some missmatch event !
        #if self.is_started == start_nstop:
        #    trace_out.simple_event(time, self.name(), not self.is_started, self.cat(), None)

        trace_ctx.trace_out.simple_event(time, self.name(), start_nstop, self.cat(), subname = self.decode_val(val))
        self.is_started = start_nstop
        if start_nstop:
            self.last_active = val
        else:
            self.last_active = None

    def end(self, trace_ctx, time):
        if self.is_started:
            self.process(trace_ctx, time, False, self.last_active)

class EventStartStopMulti(EventType):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
        self.active_event = {}
        self.async_ids = IdAllocator()
    def process(self, trace_ctx, time, start_nstop, val):
        self.assert_warn(trace_ctx.state_run, trace_ctx, time, f"event {self.name()} when not run")
        super().ts_check(time)
        #at trace startup we have initial state without +/-
        if start_nstop == None:
            start_nstop = True

        dval = self.decode_val(val)

        if start_nstop:
            #no repeated start
            assert(dval not in self.active_event)
            event_id = self.async_ids.get_id()
            self.active_event[dval] = event_id
        else:
            #no repeated stop
            assert(dval in self.active_event)
            event_id = self.active_event.pop(dval)
            self.async_ids.release_id(event_id)

        #chrome async event do not do what we whant, use simple event
        #trace_out.async_event(time, self.name(), self.decode_val(val), start_nstop)
        trace_ctx.trace_out.simple_event(time, f"{self.name()}_{event_id}", start_nstop, self.cat(), subname = dval)
    def end(self, trace_ctx, time):
        for dval in self.active_event:
            event_id = self.active_event[dval]
            trace_ctx.trace_out.simple_event(time, f"{self.name()}_{event_id}", False, self.cat(), subname = dval)
            self.async_ids.release_id(event_id)
            #print(ev, file=sys.stderr)
        self.active_event.clear()

class EventStartStopMultiByName(EventType):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
        self.active_event = {}
    def process(self, trace_ctx, time, start_nstop, val):
        self.assert_warn(trace_ctx.state_run, trace_ctx, time, f"event {self.name()} when not run")
        super().ts_check(time)
        #at trace startup we have initial state without +/-
        if start_nstop == None:
            start_nstop = True

        dval = self.decode_val(val)
        #dval = ":".join(ddval.split(':')[1:])

        if start_nstop:
            #no repeated start
            assert(dval not in self.active_event)
            self.active_event[dval] = True
        else:
            #no repeated stop
            assert(dval in self.active_event)
            self.active_event.pop(dval)
            #None

        #chrome async event do not do what we whant, use simple event
        #trace_out.async_event(time, self.name(), self.decode_val(val), start_nstop)
        trace_ctx.trace_out.simple_event(time, f"{dval}", start_nstop, self.cat(), subname = ddval)
    def end(self, trace_ctx, time):
        for dval in self.active_event:
            self.active_event[dval]
            trace_ctx.trace_out.simple_event(time, f"{dval}", False, self.cat(), subname = None)
            #print(ev, file=sys.stderr)
        self.active_event.clear()

#instant event with val
class EventVal(EventType):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
    def process(self, trace_ctx, time, start_nstop, val):
        #self.assert_warn(trace_ctx.state_run, trace_ctx, time, f"event {self.name()} when not run")
        super().ts_check(time)
        assert(start_nstop == None)
        trace_ctx.trace_out.simple_event2(time, self.name(), self.decode_val(val), cat = self.cat())

#change state
class EventState(EventType):
    def __init__(self, long_name, off_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
        self.off_name = off_name
        self.last_state = None
    def process(self, trace_ctx, time, start_nstop, val):
        self.assert_warn(trace_ctx.state_run, trace_ctx, time, f"event {self.name()} when not run")
        super().ts_check(time)
        assert(start_nstop == None)
        #first clear last event
        if self.last_state != None:
            trace_ctx.trace_out.simple_event(time, self.name(), False, self.cat(), subname = "")
        dval = self.decode_val(val)
        if dval == self.off_name:
            self.last_state = None
        else:
            trace_ctx.trace_out.simple_event(time, self.name(), True, self.cat(), subname = dval)
            self.last_state = dval

    def end(self, trace_ctx, time):
        if self.last_state != None:
            trace_ctx.trace_out.simple_event(time, self.name(), False, self.cat(), subname = "")

#value is an integer/float
class EventCount(EventType):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
    def process(self, trace_ctx, time, start_nstop, val):
        #self.assert_warn(trace_ctx.state_run, trace_ctx, time, f"event {self.name()} when not run")
        super().ts_check(time)
        assert(start_nstop == None)
        trace_ctx.trace_out.simple_count(time, self.name(), self.decode_val(val), cat = self.cat())
    def end(self, trace_ctx, time):
        self.process(trace_ctx, time, None, 0)

class EventUnknow(EventType):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
    def process(self, trace_ctx, time, start_nstop, val):
        super().ts_check(time)
        if start_nstop != None:
            if val == None:
                trace_ctx.trace_out.simple_event(time, self.name(), start_nstop, self.cat(), subname = self.decode_val(val))
            else:
                #trace_out.async_event(time, self.name(), self.decode_val(val), start_nstop)
                pass
        else:
            if self.name()[0] == 'E':
                trace_ctx.trace_out.simple_event2(time, self.name(), self.decode_val(val), cat = self.cat())
            else:
                trace_ctx.trace_out.simple_event2(time, self.name(), val)

#custom event
class EventWakeLock(EventStartStopSingle):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
        self.last_active = None
    def process(self, trace_ctx, time, start_nstop, val):
        #if not start_nstop and val is None:
        if not start_nstop:
            val = None
        self.last_active = val
        dval = self.decode_val(val)

        #XXX wakelock before trace start ???
        #if not start_nstop and dval not in self.active_event:
        #    return
        #if start_nstop and dval in self.active_event:
        #    return

        super().process(trace_ctx, time, start_nstop, val)
        if dval is not None and start_nstop and "alarm*:" in dval:
            trace_ctx.trace_out.simple_event2(time, dval, "pending", cat = "alarm")
        trace_ctx.state_wl = start_nstop

class EventRun(EventStartStopSingle):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
    def process(self, trace_ctx, time, start_nstop, val):
        assert(trace_ctx.stop_run_ts == 0)

        #no two consecutive start or stop
        self.assert_warn(trace_ctx.state_run!=start_nstop, trace_ctx, time, f"invalid run state {start_nstop}")
        if trace_ctx.state_run == start_nstop:
            return

        if start_nstop:
            #no wake lock before run start
            self.assert_warn(not trace_ctx.state_wl, trace_ctx, time, "wake lock before run")
            trace_ctx.state_run = True
            trace_ctx.stop_run_ts = 0

        super().process(trace_ctx, time, start_nstop, val)

        if not start_nstop:
            trace_ctx.stop_run_ts = time

class EventWakeReason(EventVal):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
    def process(self, trace_ctx, time, start_nstop, val):
        super().process(trace_ctx, time, start_nstop, val)
        ddval = self.decode_val(val)
        dval = ddval.replace("47:glink-native-rpm-glink:", "")
        if not dval.startswith("0:Abort:"):
            #XXX
            dval = dval.replace("44:(unnamed):", "")
            dval = dval.replace("51:(unnamed):", "")
            dval = dval.replace("16:mpm:", "")
            if "slate_spi" not in dval and ":Abort" in dval:
                pos = dval.rfind(':')
                dval = dval[0:pos-len(":Abort")]
            trace_ctx.trace_out.simple_event2(time, dval, ddval, cat = "wake reason")

class EventCpu(EventType):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
        #self.cpu_user = EventCount(long_name + '_user', position, cat)
        #self.cpu_sys = EventCount(long_name + '_sys', position, cat)
        self.last_time = 0
    def process(self, trace_ctx, time, start_nstop, val):
        #        // Time (in 1/100 second) spent in user space and the kernel since the last step.
        #userTime,systemTime
        #can be followed by
        # Top three apps using CPU in the last step, with times in 1/100 second.
        print("cpu", file=sys.stderr)
        split = val.split(':')
        #XXX don't use utc time that can change
        if self.last_time != 0:
            time_delta = (time - self.last_time) / 1000000
            #XXX the computed value seem wrong. Better use pst values
            #print(f"{int(split[0])} {time_delta}")
            #self.cpu_user.process(trace_out, time, start_nstop, int(split[0])/time_delta)
            #self.cpu_sys.process(trace_out, time, start_nstop, int(split[1])/time_delta)
        self.last_time = time

class EventCpuStat(EventType):
    def __init__(self, long_name, position, cat = 'other', decode_val = None):
        super().__init__(long_name, position, cat, decode_val)
        self.cpu_user = EventCount(long_name + '_user', position, cat)
        self.cpu_sys = EventCount(long_name + '_sys', position, cat)
        self.cpu_idle = EventCount(long_name + '_idle', position, cat)
        self.cpu_total = EventCount(long_name + '_total', position, cat)
        self.cpu_time = EventCount(long_name + '_time', position, cat)
        self.cpu_ttime = EventCount(long_name + '_ttime', position, cat)
        self.last_time = 0
    def process(self, trace_ctx, time, start_nstop, val):
        #        // Time (in 1/1000 second) spent in user space and the kernel since the last step.
        #userTime,systemTime,io,irq,softirq,idle
        #can be followed by
        # Top three apps using CPU in the last step, with times in 1/100 second.
        split = val.split(':')
        #XXX total don't include suspend time...
        total = int(split[0]) + int(split[1]) + int(split[2]) + int(split[3]) + int(split[4]) + int(split[5])
        #print(f"{int(split[0])} {total}")
        #print(f"{val}")
        if self.last_time != 0:
            time_delta_ms = (time - self.last_time) / 1000
            self.cpu_user.process(trace_ctx, self.last_time, start_nstop, int(split[0])/time_delta_ms * 100)
            self.cpu_sys.process(trace_ctx, self.last_time, start_nstop, int(split[1])/time_delta_ms * 100)
            self.cpu_idle.process(trace_ctx, self.last_time, start_nstop, int(split[5]) /time_delta_ms * 100)
            self.cpu_total.process(trace_ctx, self.last_time, start_nstop, total / time_delta_ms * 100)
            #self.cpu_time.process(trace_ctx, self.last_time, start_nstop, time_delta_s*100)
            #self.cpu_ttime.process(trace_ctx, self.last_time, start_nstop, time / 1000000 *100)
        self.last_time = time

class BatteryStats:

    def event_decode_val_pool(self, val):
        key = int(val)
        return f"{self.pool[key][0]}:{self.pool[key][1][1:-1]}"

    def event_decode_val_temp(self, val):
        key = int(val) / 10.0
        return f'{key}'

    def event_decode_val_radio_qual(self, val):
        conv = [ "none", "poor", "moderate", "good", "great" ]
        key = int(val)
        return f"{conv[key]}"

    def event_decode_val_screen_brigth(self, val):
        conv = [ "dark", "dim", "medium", "light", "bright" ]
        key = int(val)
        return f"{conv[key]}"

    def event_decode_val_wifi_supplicant(self, val):
        conv = { 'inv': "invalid", 'dsc': "disconn", 'dis': "disabled", 'inact': "inactive", 'scan': "scanning",
                'auth': "authenticating", 'ascing': "associating", 'asced': "associated", '4-way': "4-way-handshake",
                'group': "group-handshake", 'compl': "completed", 'dorm': "dormant", 'uninit': "uninit" }
        return f"{conv[val]}"

    def event_decode_val_gnss_qual(self, val):
        conv = [ "poor", "good" ]
        try:
            key = int(val)
        except:
            return val

        return f"{conv[key]}"

    def __init__(self):
        self.trace_ctx = TraceContext(TraceOutPerfettoJson())
        self.pool = []
        self.history_data = []
        self.cat_prio = (
                ('running', 1.0),
                ('others', 2.0),
                ('Jobs', 1.9),
                ('Sync', 4.0),
                ('fg app', 5.0),
                ('misc', 6.0),
                ('radio', 7.0),
                )
        self.events = {
                    'r' : EventRun('running', 1.0, cat = 'running'), #no args
                    's' : EventStartStopSingle('sensor', 1.3, cat = 'sensors'),
                    'g' : EventStartStopSingle('gps', 1.3, cat = 'sensors'),
                    'Gss' : EventState('gps quality', None, 1.3, cat = 'sensors', decode_val = self.event_decode_val_gnss_qual),
                    'a' : EventStartStopSingle('audio', 1.3, cat = 'sensors'),
                    'fl' : EventStartStopSingle('flashlight', 1.3, cat = 'sensors'),
                    'ca' : EventStartStopSingle('camera', 1.3, cat = 'sensors'),

                    'Etp' : EventStartStopSingle('Top app', 1.2, cat = 'running', decode_val = self.event_decode_val_pool),
                    'Ejb' : EventStartStopMulti('JobScheduler', 1.3, cat = 'Jobs', decode_val = self.event_decode_val_pool),
                    'Esy' : EventStartStopMulti('SyncManager', 1.3, cat = 'Sync', decode_val = self.event_decode_val_pool),
                    'Efg' : EventStartStopMulti('Forground app', 1.3, cat = 'fg app', decode_val = self.event_decode_val_pool),
                    'Epi' : EventVal('package install', 1.3, cat = 'misc', decode_val = self.event_decode_val_pool),
                    'di' : EventState('doze', 'off', 1.3, cat = 'misc'),
                    #wake
                    'wr' : EventWakeReason('wakeup reason', 1.1, cat = 'running', decode_val = self.event_decode_val_pool),
                    #XXX app wakeup need app decoding from uid
                    'Ewa' : EventVal('App processor wakeup', 1.1, cat = 'running', decode_val = self.event_decode_val_pool),
                    #wake lock
                    'w' : EventWakeLock('wake_lock', 1.2, cat = 'running', decode_val = self.event_decode_val_pool),
                    'Elw' : EventStartStopMulti('Long wakelock', 1.2, cat = 'running', decode_val = self.event_decode_val_pool),
                    'Ewl' : EventStartStopMulti('wakelock full', 1.2, cat = 'wakelock full', decode_val = self.event_decode_val_pool),
                    'Eal' : EventStartStopMulti('alarm', 1.2, cat = 'alarm full', decode_val = self.event_decode_val_pool),
                    #battery
                    'Bl': EventCount('Battery', 1.0, cat = 'running'),
                    'Bcc': EventCount('Coloumb charge ', 1.0, cat = 'running'),
                    'Bt': EventCount('Bat Temp', 1.0, cat = 'misc', decode_val = self.event_decode_val_temp),
                    'Bv': EventCount('Bat Volt', 1.0, cat = 'misc'),
                    'BP': EventStartStopSingle('Plugged', 1.0, cat = 'misc'),
                    'ch': EventStartStopSingle('Charging on', 1.0, cat = 'misc'),
                    #screen
                    'S': EventStartStopSingle('Screen', 1.0, cat = 'running'), #no args
                    'Esw' : EventVal('Screen wakeup', 1.0, cat = 'running', decode_val = self.event_decode_val_pool),
                    'Sd': EventStartStopSingle('Screen doze', 1.0, cat = 'misc'), #no args
                    'Sb': EventState('Screen brigthness', None, 1.0, cat = 'misc', decode_val = self.event_decode_val_screen_brigth), #no args
                    #network
                    ## Ecn for 'Network connectivity
                    #mobile radio
                    'Pr' : EventStartStopSingle('Mobile radio active', 1.1, cat = 'radio'),
                    'Pss' : EventState('Mobile radio strength', 'none', 1.1, cat = 'radio', decode_val = self.event_decode_val_radio_qual),
                    #Pcn
                    #Pst
                    #Chtp
                    #wifi
                    'Wr' : EventStartStopSingle('Wifi radio', 1.1, cat = 'radio'),
                    'Wss' : EventState('Wifi radio strength', 'none', 1.1, cat = 'radio', decode_val = self.event_decode_val_radio_qual),
                    'Ws' : EventStartStopSingle('Wifi scan', 1.1, cat = 'radio'),
                    'Wm' : EventStartStopSingle('Wifi muticast', 1.1, cat = 'radio'),
                    'Wl' : EventStartStopSingle('Wifi full lock', 1.1, cat = 'radio'),
                    'W' : EventStartStopSingle('Wifi on', 1.1, cat = 'radio'),
                    'Ww' : EventStartStopSingle('Wifi running', 1.1, cat = 'radio'),
                    'Wsp' : EventState('Wifi supplicant', None, 1.1, cat = 'radio', decode_val = self.event_decode_val_wifi_supplicant),
                    #bluetooth
                    'b' : EventStartStopSingle('Bluetooth on', 1.1, cat = 'radio'),
                    'bles' : EventStartStopSingle('Bluetooth scan', 1.1, cat = 'radio'),
                    #special case
                    'Dcpu' : EventCpu('cpu', 1.0, cat = 'misc'),
                    'Dpst' : EventCpuStat('cpu', 1.0, cat = 'misc'),
                }

        for k, event in self.events.items():
            print(f"{event.name()} {event.cat()}, {event.position()}", file=sys.stderr)

        #time in us
        self.time_offset = 0
        self.time_last_event = 0

    def find_event(self, key):
        if key not in self.events:
            self.events[key] = EventUnknow(key, 99.0, decode_val = self.event_decode_val_pool)
        return self.events[key]

    def end_events(self, time):
        for key in self.events:
            self.events[key].end(self.trace_ctx, time)

    def parse_history(self):
        self.history_data = sorted(self.history_data, key=itemgetter(0))
        print("[")
        for etime, line in self.history_data:

                split = line.split(',')
                utctime = etime + self.time_offset

                #assert(utctime >= self.time_last_event)

                if len(split) == 3:
                    ssplit = split[2].split(':')

                    timedelta = int(ssplit[0]) * 1000
                    #iterate over other arg
                    iterator = iter(ssplit[1:])
                    try:
                        while True:
                            element = next(iterator)
                            if element == "RESET":
                                #do nothing
                                element = ""
                            elif element == "START":
                                self.end_events(utctime)
                            elif element == "TIME":
                                #time in ms. convert it to us
                                #XXX battery historian seem to remove timedelta for computed time !!!!
                                new_time = int(next(iterator)) * 1000
                                print(f"time:{utctime} new_time:{new_time} diff:{new_time-utctime}", file=sys.stderr)
                                if utctime == 0:
                                    utctime = new_time

                                #assert(new_time > self.time - timedelta)
                                if new_time < utctime - timedelta:
                                #if new_time < self.time_last_event:
                                    ### XXX backward time not supported
                                    #ignore new time setting in that case ???
                                    self.trace_ctx.trace_out.simple_event2(utctime, "set time", f"past : {(new_time - utctime)/1000000} {timedelta/1000000}", cat = "running")
                                    new_time = utctime
                                elif new_time == utctime:
                                    self.trace_ctx.trace_out.simple_event2(new_time, "set time", "same", cat = "running")
                                elif new_time < utctime:
                                    self.trace_ctx.trace_out.simple_event(new_time, "set time", True, "running", subname = f"back {(new_time - utctime)/1000000}")
                                    self.trace_ctx.trace_out.simple_event(utctime, "set time", False, "running")
                                else:
                                    self.trace_ctx.trace_out.simple_event(utctime, "set time", True, "running", subname = f"advance {(new_time - utctime)/1000000}")
                                    self.trace_ctx.trace_out.simple_event(new_time, "set time", False, "running")
                                self.time_offset = new_time - etime

                    except StopIteration:
                        pass
                else:
                    if split[3].startswith("Dpst="):
                        #XXX this event is split by ','
                        #make it split by ':'
                        tmp = ",".join(split[3:])
                        tmp = tmp.replace(",", ":")
                        tmp = "a,b,c," + tmp
                        split = tmp.split(',')

                    #switch run state after we process all even with same ts
                    if self.trace_ctx.stop_run_ts != 0 and self.trace_ctx.stop_run_ts < utctime:
                        self.trace_ctx.stop_run_ts = 0
                        self.trace_ctx.state_run = False
                        #there should be no active wakelock
                        assert(not self.trace_ctx.state_wl)

                    iterator = iter(split[3:])
                    try:
                        while True:
                            element = next(iterator)
                            date = datetime.datetime.fromtimestamp(utctime/1000000, datetime.timezone(datetime.timedelta(minutes=0)))
                            print(f"time:{utctime} event:{element} {date} {line}", file=sys.stderr)

                            ssplit = element.split("=", 1)

                            if element[0] == '+' or element[0] == '-':
                                start_nstop = element[0] == '+'
                                key = ssplit[0][1:]
                            else:
                                start_nstop = None
                                key = ssplit[0]

                            if len(ssplit) == 1:
                                val = None
                            else:
                                val = ssplit[1]

                            #no start/stop event should have a value
                            assert(start_nstop != None or val != None)

                            #here we have
                            # key : event name
                            # start_nstop (optional) : event start/stop
                            # val (optional) : event value

                            event = self.find_event(key)

                            event.process(self.trace_ctx, utctime, start_nstop, val)

                            self.time_last_event = utctime

                    except StopIteration:
                        pass
        self.end_events(self.time_last_event)
        print("]")

    def parse(self):
        time = 0

        for v in self.cat_prio:
            cat_name, cat_prio = v
            print(f"{cat_name} {cat_prio}", file=sys.stderr)
            #self.trace_ctx.trace_out.cat_prio(cat_name, cat_prio)

        for line in sys.stdin:
            line = line[:-1]
            if line[len(line)-1] == "\r":
                line = line[:-1]
            if line.startswith("9,hsp"):
                split = line.split(',', 4)
                assert(len(split) == 5)
                #is array more efficient than dict ???
                #could be .append (should be in order)
                self.pool.insert(int(split[2]), (split[3], split[4]))
            elif line.startswith("9,h,"):
                split = line.split(',')
                if len(split) == 3:
                    #command or only time update
                    ssplit = split[2].split(':')
                    #account time
                    timedelta = int(ssplit[0]) * 1000
                    time += timedelta
                    self.history_data.append((time, line))
                else:
                    #event
                    assert(len(split) >= 4)
                    timedelta = int(split[2]) * 1000

                    time += timedelta
                    self.history_data.append((time, line))
        #a second pass is needed : event are not in order in recent android version
        self.parse_history()



BatteryStats().parse()
