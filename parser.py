# coding=utf-8
import re,sys, os
import argparse as ap
from Call import *
import subprocess, time
from collections import deque
# get_call_ids_for_number = "grep %s full | egrep -o 'C-.{8}' | sort | uniq | tr '\n' ' '"

# // Секция с определением регулярных выражений для поиска номеров А Б , начала/конца звонка по call_id
# // Мы получили call_ids всех звонков для данного номера

# // 2
# Поиск всех звонков для диапазона времени , или от конкретной точки.
#

#################   START REGULAR DEFENITION    ###################
msg_re_get = r'^\[(?P<date>.*?)\] (?P<type>VERBOSE|NOTICE|WARNING)\[(?P<log_id>.*?)\]((\[(?P<call_id>.*?)\](?P<msg_call>.*))|(?P<msg_aster>.*))'
# start_call_re = re.compile('^\[(?P<date>.*?)\] (?P<type>VERBOSE|NOTICE|WARNING)\[(?P<log_id>.*?)\]\[(?P<call>.*?)\]|(?P<msg>.*)')

#################   END REGULAR DEFENITION      ###################

#################   START FUNCTION DEFINITION     ###################
def usage():
    print('''
Usage:
    log.py [-tstart='date time'] file
           [-tend='date time'] file
           [-tstart='date time -tend='date time'] file
           [-tday='date'] file
           [-tlast='num min|num hour|day default=10min'] file
           [-anum='number'] file
           [-bnum='number'] file
           [-call_id='call id'] file
           [-chan_id='channel id'] file
           [-cause_id='num|name'] file
    ''')
# Help how to use script

def argv_parser():
    '''tstart  tend  tlast  anum  bnum  call_id   channel_id   cause_id'''
    parser = ap.ArgumentParser(description='a|b num; start_time|end_time; cause_id; chan_id; call_id')
    # parameters to parse
    parser.add_argument('--tstart','-ts', default=0, help='provide start time for log')     # DATE
    parser.add_argument('--tend','-te', default=0, nargs='+',  help = 'provide end time for log') # DATE
    parser.add_argument('--tday','-td', default=0, help = 'provide day to check calls')  #DATE
    parser.add_argument('--tlast', '-tl', default='10m', type=str, help = 'provide last period in mins|hours')     #MIN|HOUR|DAY
    parser.add_argument('--anum', default=0, help = 'provide A number')    # NUMBER
    parser.add_argument('--bnum', default=0, help = 'provide B number')   # NUMBER
    parser.add_argument('--call_id', '-cid', default=0, nargs='*', help = 'provide call id')   # call_id - LIST
    parser.add_argument('--channel_id', '-chid', default=0, help = 'provide CHANNEL ID')   # CHAN_ID - STRING
    parser.add_argument('--cause_id', '-caid', default=0 , nargs = '*', metavar = 'CAUSEID', help = 'provide CAUSE ID')   # CAUSE_ID - STRING
    # parameters for detalization
    parser.add_argument('--dump', action='store_true', help = 'show var dumps')   # ADDITIONS - PARAM
    parser.add_argument('--with-dialplan', action='store_true', help = 'сравнить с диалпланом из extensions.conf')    # ADDITIONS - DIALPLAN
    parser.add_argument('--full', action='store_true', help = 'Equal --dump + --with-dialplan')
    # list common statistics
    parser.add_argument('--list', '-l', action = 'store_true', help = 'list all or for specified range or day')     # ADDITION PARAM - LIST CALLS
    parser.add_argument('--file','-f', required=True, help='Provide file for parsing')
    return parser
# Задает параметры и создает парсер; return parser

def check_params(ns   # namespace - from argparse - namespace   return void
                 ):
    '''Проверка переданных параметров tstart tend tdata'''
    ns.wrong_params = []
    ns.correct = ''
    if not hasattr(ns, 'tlast'): ns.tlast = ''
    def check_data(date_time):
        # print(date_time)
        if len(date_time.split(' ')) == 2:  # проверяем содержит ли дату И время
            if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', date_time): pass
            else:
                # print(date_time)
                print('''Wrong format of date, need: YYYY-MM-DD HH:MM:SS''')
                ns.correct = False
                ns.wrong_params.append(date_time)
        #  Если передан один параметр - дата.
        elif re.match(r'^\d{4}-\d{2}-\d{2}$',date_time.strip()): pass
        #  Если передан один параметр - время.
        elif re.match(r'^\d{2}:\d{2}:\d{2}$',date_time.strip()): pass
        else:
            print('wrong time or date format ,YYYY-MM-DD HH:MM:DD', date_time)
            ns.correct = False
            ns.wrong_params.append(date_time)

    def check_number(num):
        '''Проверка формата номера'''
        if re.match(r'^\d{1,11}$', num):
            pass
        else:
            print('Wrong format of number , need X[XXXXXXXXXX]', num)
            ns.correct = False
            ns.wrong_params.append(num)


    # print(ns.tstart, ns.tend)
    if ns.tstart:
        ns.tstart = ns.tstart.strip()
        check_data(ns.tstart)
        # print('if ns.tstart , ns.tend =  ', ns.tend[0])
    if ns.tend:
        ns.tend[0] = ns.tend[0].strip()
        # print('if ns.tend', ns.tend)
        check_data(ns.tend[0].strip())
    if ns.tday:
        ns.tday = ns.tday.strip()
        # print('if ns.tday', ns.tday)
        check_data(ns.tday)
    if ns.anum: ns.anum = ns.anum.strip(); check_number(ns.anum)
    if ns.bnum: ns.bnum = ns.bnum.strip(); check_number(ns.bnum)
    if ns.tlast:
        ns.tlast = ns.tlast.strip()
        if re.match(r'^\d{1,3}[mhd]$', ns.tlast):
            pass
        else:
            print('Wrong param', ns.tlast); ns.correct = False; ns.wrong_params.append(ns.tlast)
    if os.path.isfile(ns.file): pass
    else:
        print('File not exists', ns.file)
    if not ns.correct and ns.correct != '': print('Wrong param(s)', ns.wrong_params); exit(1)
# Проверяет на корректность переданные параметры

def parse_start_end_calls(data):    # return array of calls type Call
    re_start_call = re.compile(r'^\[(?P<date>.*?)\] VERBOSE\[.*\]\[(?P<call_id>C-\w{8})\] netsock2.c: .+$')
    file_true = False
    if type(data) != 'str':
        data = data.split('\n')
        for line in data:
            print(line)
    else:
        data = open(data, 'r')
        data_true = True
    calls_id = []
    calls = {}
    for line in data:
        res = re_start_call.match(line)
    # print(res, line)
        if res:
            if res.group('call_id') not in calls_id:
                # print(res.group('date'), res.group('call_id'), res.string)
                calls_id.append(res.group('call_id'))
                call = Call(); call.time_start = res.group('date').split(' ')[1]; call.call_id = res.group('call_id')
                call.date_time = res.group('date'); call.date = res.group('date').split(' ')[0]
                calls[call.call_id] = call
                continue
            else:
                calls[res.group('call_id')].time_start = res.group('date').split(' ')[1]
                re_end_call = re.compile(r'^\[(?P<date>.*?)\] VERBOSE\[.*\]\[(?P<call_id>C-\w{8})\] app_stack.c:     -- SIP.*complete.*$')
                res = re_end_call.match(line)
                if res:
                    if res.group('call_id') not in calls_id:
                        calls_id.append(res.group('call_id'))
                        call = Call(); call.time_end = res.group('date').split(' ')[1]; call.call_id = res.group('call_id')
                        calls[call.call_id] = call
                    else:
                        calls[res.group('call_id')].time_end = res.group('date').split(' ')[1]
    if file_true:
        data.close()
    return calls_id, calls

# def parse_end_calls(calls, file):   # void
#     def
#     with open(file, 'r') as f:
#         for i in range(0, len(calls)):
#             re_end_call = re.compile(r'^\[(?P<date>.*?)\] VERBOSE\[.*\]\[%s\] app_stack.c:     -- SIP.*$' % calls[i].call_id)
#
#         i = 0
#         for call in calls:
#             re_end_call = re.compile(r'^\[(?P<date>.*?)\] VERBOSE\[.*\]\[%s\] app_stack.c:     -- SIP.*$' % call.call_id)
#             for line in file:
#                 res = re_end_call.match(line)
#
#                 if res:
#                     call.time_end = res.group('date').split(' ')[1]
#                     calls[i] = call
#                     break

def grep_call(param, file):
    # call_id = calls_id.pop()
    call_grep = subprocess.check_output(['grep', param, file])  #encoding='utf8'
    return call_grep

def getABnum(grep_call):
    A_re = re.compile(r'.*"_OurNum=(?P<cid>\w+)".*')
    B_re = re.compile(r'.*Executing \[(?P<exten>\w+)@.*:1\].*')
    grep_call = grep_call.split('\n') # 1 line to list of lines
    A_num = 0
    B_num = 0
    for line in grep_call:
        if line:
            if not A_num:
                A = A_re.match(line)
                if A:
                    A_num = A.group('cid')
                    # print(A_num)
                    continue
            else:
                if not B_num:
                    B = B_re.match(line)
                    if B:
                        B_num = B.group('exten')
                        # print(B_num)
    return A_num, B_num

def parse_log_msg():
    pass

def formatListCalls(calls_id, calls):
    for key in calls_id:
        grep_call_res = grep_call(calls[key].call_id, ns.file)
        calls[key].anum, calls[key].bnum = getABnum(grep_call_res)
        # break

    for key in calls_id:  # Перебор всех найденных звонков и вывод табличном виде
        print(calls[key].date.ljust(12) + " | " + str(getattr(calls[key], 'time_start', 0)).ljust(12) + " | " + str(
            getattr(calls[key], 'time_end', 0)).ljust(12) \
              + " | " + calls[key].call_id.ljust(12) + " | A: " + str(getattr(calls[key], 'anum', 0)).ljust(
                    12) + " | B: " \
              + str(getattr(calls[key], 'bnum', 0)).ljust(12))
    print(len(calls.keys()))
    print("--- %s seconds ---" % (time.time() - start_time))
#################   END FUNCTION DEFENITION     ###############

calls_id = []
calls = {}
if __name__ == '__main__':
    if len(sys.argv) > 1:
        parser = argv_parser()
        ns = parser.parse_args()
        check_params(ns)
        # print(ns.tstart, ns.tend[0])
        print(ns)
        start_time = time.time()
        if ns.list:
            calls_id, calls = parse_start_end_calls(ns.file)
            formatListCalls(calls_id, calls)

        if ns.anum:
            data = grep_call(ns.anum, ns.file)
            calls_id, calls = parse_start_end_calls(data)
            formatListCalls(calls_id, calls)

        # if ns.bnum

        # print(type(grep_call))
        # print(grep_call)
        # a, b = getABnum(grep_call)
        # print(a, b)



