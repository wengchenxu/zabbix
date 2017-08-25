#encoding=UTF8
'''
mongodb���
@author: qiueer
2016-02-15
'''

import commands
import sys
import os
from optparse import OptionParser
import re
import time
import platform
import json
import pprint
import types

from qiueer.python.QLog import Log

def docmd(command,timeout=300, raw=False):
        '''
        ���ܣ�
                ִ������
        ������command�������Լ������/ѡ��
                timeout�����ʱʱ�䣬��λ��
                debug���Ƿ�debug��True���debug��Ϣ��False�����
                raw����������Ƿ�ΪԪ�ص������True�ǣ�False�Ὣ�����ÿһ��ȥ���ո񡢻��з����Ʊ���ȣ�Ĭ��False
        ���أ�
                ����3��Ԫ�ص�Ԫ�飬ǰ����Ԫ��������list��������Ԫ��������int����һ��list�洢stdout��������ڶ���list�洢stderr�����������int�洢����ִ�еķ����룬����-1��ʾ����ִ�г�ʱ
        ʾ����
                cmd.docmd("ls -alt")
        '''
        import subprocess, datetime, os, time, signal
        start = datetime.datetime.now()

        ps = None
        retcode = 0
        if platform.system() == "Linux":
                ps = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        else:
                ps = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        while ps.poll() is None:
                time.sleep(0.2)
                now = datetime.datetime.now()
                if (now - start).seconds > timeout:
                        os.kill(ps.pid, signal.SIGINT)
                        retcode = -1
                        return (None,None,retcode)
        stdo = ps.stdout.readlines()
        stde = ps.stderr.readlines()
        
        if not ps.returncode:
                retcode = ps.returncode
        
        if raw == True:  #ȥ����ĩ���з�
                stdo = [line.strip("\n") for line in stdo]
                stde = [line.strip("\n") for line in stde]
        
        if raw == False: #ȥ����ĩ���з����Ʊ�����ո��
                stdo = [str.strip(line) for line in stdo]
                stde = [str.strip(line) for line in stde]

        return (stdo,stde,retcode)


def get_logstr(list_dict, max_key_len=16, join_str="\n"):
    log_str = ""
    for conf in list_dict:
        for (key,val) in dict(conf).iteritems():
            log_str = log_str + str(key).ljust(max_key_len) + ": " + str(val) + join_str
    log_str = log_str.strip() # ȥ��β�� \n
    return log_str

def get_user_passwd_by_port(conffile, port):
    if os.path.exists(conffile) == False:
        return (None,None)
    with open(conffile,'r') as fd:
        alllines = fd.readlines()
        for line in alllines:
            line = str(line).strip()
            if not line or line.startswith("#"):continue
            ln_ary = re.split('[ ,;]+', line)
            if len(ln_ary) < 3:continue
            if str(port) == ln_ary[0]:
                return (ln_ary[1],ln_ary[2])
    return (None, None)

class MGdb(object):

    
    def __init__(self, iphost="127.0.0.1", port=27017, username=None, password=None, force=False, debug=True):
        self._iphost = iphost
        self._port = port
        self._username = username
        self._password = password
        self._force = force
        
        self._logpath = "/tmp/zabbix_mongodb.log"
        self._cache_file = "/tmp/zabbix_mongodb_cache_%s.txt" %(port)
        if not port:
            self._cache_file = "/tmp/zabbix_mongodb_cache.txt"
    
        self._logger = Log(self._logpath,is_console=debug, mbs=5, count=5)
        
    def get_logger(self):
        return self._logger

    def get_port_list(self):
        # sudoȨ�ޣ���������
        # [root@localhost ~]# tail -n 2 /etc/sudoers
        # Defaults:zabbix   !requiretty 
        # zabbix ALL=(root) NOPASSWD:/bin/netstat

        binname = "mongod"
        cmdstr = "sudo netstat  -nlpt | grep '%s' | awk '{print $4}'|awk -F: '{print $2}'" % (binname)
        disk_space_info = []
        (stdo_list, stde_list, retcode) = docmd(cmdstr, timeout=3, raw = False)
        
        log_da = [{"cmdstr": cmdstr},{"ret": retcode},{"stdo": "".join(stdo_list)}, {"stde": "".join(stde_list)}]
        logstr = get_logstr(log_da, max_key_len=10)
        
        if retcode !=0:
            self._logger.error(logstr)
            return {}
        else:
            self._logger.info(logstr)
            
        data = list()

        for port in stdo_list:
            port = int(str(port).strip())
            data.append({"{#MONGODB_PORT}": port})
        import json
        return json.dumps({'data': data}, sort_keys=True, indent=7, separators=(",",":"))
    
    def _get_result(self, iphost=None, port=None, username=None, password=None):
        try:
            hostname= iphost if iphost else self._iphost
            port = port if port else self._port
            username = username if username else self._username
            password = password if password else self._password
            resobj = None
            
            if self._force == False:
                if os.path.exists(self._cache_file):
                    with open(self._cache_file, "r") as fd:
                        alllines = fd.readlines()
                        fd.close()
                        if alllines and len(alllines)>1:
                            old_unixtime = int(str(alllines[0]).strip())
                            now_unixtime = int(time.time())
                            if (now_unixtime - old_unixtime) <= 60: ## 1min��
                                resobj = str(alllines[1]).strip()
                                resobj = json.loads(resobj)

                if resobj:
                    log_da = [{"msg": "Get From Cache File"}, {"content": str(resobj)}]
                    logstr = get_logstr(log_da, max_key_len=10)
                    self._logger.info(logstr)
                    return resobj
            
            pbinpaths = [
                         "/usr/local/mongodb/bin/mongo",
                         "/home/qiueer/mongodb/mongodb/bin/mongo",
            ]
            cmdstr = None
            for bp in pbinpaths:
                if os.path.exists(bp):
                    cmdstr = "echo 'db.serverStatus()' | %s admin --host '%s'  --port %s --quiet" % (bp, hostname, port)
                    if username and password:
                        cmdstr = "echo 'db.serverStatus()' | %s admin --host '%s'  --port %s -u %s -p %s --quiet" % (bp, hostname, port, username, password)
                    break
            if not cmdstr:
                return None

            (stdo_list, stde_list, retcode) = docmd(cmdstr, timeout=3, raw = False)
            
            log_da = [{"cmdstr": cmdstr},{"ret": retcode},{"stdo": None if not stdo_list else "".join(stdo_list)}, {"stde": None if not stde_list else"".join(stde_list)}]
            logstr = get_logstr(log_da, max_key_len=10)
        
            if retcode !=0:
                    self._logger.error(logstr)
                    return None
            else:
                self._logger.info(logstr)
            
            stdo_str = "".join(stdo_list)
            stdo_str = stdo_str.replace("NumberLong(", "").replace(")", "").replace("ISODate(", "")
            #print stdo_str
            resobj = json.loads(stdo_str)
            now_unixtime = int(time.time())
            with open(self._cache_file, "w") as fd:
                fd.write(str(now_unixtime)+"\n")
                fd.write(stdo_str)
                fd.close()

            return resobj
        except Exception as expt:
            import traceback
            tb = traceback.format_exc()
            self._logger.error(tb)

    def get_item_val(self, *items):
        resobj = self._get_result()
        src_res = resobj
        for item in items:
            if resobj and type(resobj) == types.DictType and resobj.has_key(item):
                resobj = resobj[item]
        if resobj == None or resobj == src_res:
            resobj = 0
        return resobj
    
    def get_result(self):
        return self._get_result()
    
    def get_item_tval(self,  items, val_type="int"):
        val = self.get_item_val(*items)
        if val == None:return None  #0Ҳ���������
        if val_type == "int":
            return int(val)
        if val_type == "float":
            fval = "%.2f" % (val)
            return float(fval)
        if val_type == "str":
            return str(val)
        
        return int(val)
    
    def print_all_key_val(self):
        resobj = self._get_result()
        print json.dumps(resobj, indent=4)

    

def main():
#     pprint.pprint(MGdb()._get_result())
#     sys.exit(1)
#     mg = MGdb(debug=False)
#     mg.print_all_key_val()
#     sys.exit(0)

    usage = "usage: %prog [options]\n Fetch mongodb status"
    parser = OptionParser(usage)
    
    parser.add_option("-l", "--list",  
                      action="store_true", dest="is_list", default=False,  
                      help="if list all port")

    parser.add_option("-H", "--host", action="store", dest="host", type="string", default='localhost', help="Connect to memcached host.")

    parser.add_option("-p", 
                      "--port", 
                      action="store", 
                      dest="port", 
                      type="int", 
                      default=27017, 
                      help="the port for mongodb, for example: 27017")
    
    parser.add_option("-u", 
                      "--user", 
                      action="store", 
                      dest="username", 
                      type="string", 
                      default=None, 
                      help="username")
    
    parser.add_option("-P", 
                      "--password", 
                      action="store", 
                      dest="password", 
                      type="string", 
                      default=None, 
                      help="password")

    parser.add_option("-i", 
                      "--item", 
                      dest="item", 
                      action="store",
                      type="string", 
                      default=None, 
                      help="which item to fetch")
    
    parser.add_option("-f", "--force",  
                      action="store_true", dest="force", default=False,  
                      help="if get from cache")
    
    parser.add_option("-d", "--debug",  
                      action="store_true", dest="debug", default=False,  
                      help="if open debug mode")
    
    (options, args) = parser.parse_args()
    if 1 >= len(sys.argv):
        parser.print_help()
        return

    hostname = options.host
    port = options.port
    
    conffile = "/usr/local/public-ops/conf/.mongodb.passwd"
    username = options.username
    password = options.password
    
    if password == None or username == None:
        (username, password) = get_user_passwd_by_port(conffile, port)
        #print "Get (username=%s,password=%s) From Config File By port:%s" % (username, password, port)

    monitor_obj = MGdb(iphost=hostname, port=port, username=username, password=password, debug=options.debug, force=options.force)
    
    if options.is_list == True:
        print monitor_obj.get_port_list()
        return
    
    try:
        item = options.item
        item_ary = re.split("\.", item)
        print monitor_obj.get_item_tval(item_ary)

    except Exception as expt:
        import traceback
        tb = traceback.format_exc()
        monitor_obj.get_logger().error(tb)


if __name__ == '__main__':
    main()