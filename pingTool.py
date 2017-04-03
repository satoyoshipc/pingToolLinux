#!/usr/bin/python
# vim: fileencoding=utf-8
try:
    import json
except ImportError:
    import simplejson as json
    
import subprocess
import os
import sys
import datetime
import logging.config
logging.config.fileConfig("logging.conf")
logger = logging.getLogger()

global ERRORCOUNT
global REPAIRCOUNT
global JSONFile
global IP_LIST_FILE
global TRAPSERVER

#----------------------------------------------------
#トラップ送信する連続障害回数
ERRORCOUNT = 20
#トラップ送信する連続復旧回数
REPAIRCOUNT = 1
#結果出力ファイル
JSONFile = "tmpfile.json"
#ホストIPアドレス一覧ファイル
IP_LIST_FILE = "HostListFile"
#トラップサーバ
#TRAPSERVER = "192.168.20.62"
TRAPSERVER = "192.168.12.174"
#システムプロパティファイル
SYSTEMFILE_PATH = "/usr/local/SWing/conf/common/systemstate.properties"
#----------------------------------------------------

HISTjson =  []
outjson = []
filejson = []

#ログ出力

#logger.warn("ERROR OUT")

if os.path.isfile(JSONFile):

    #読み込み
    fi = open(JSONFile, 'r')
    try:
        HISTjson = json.load(fi)
    except Exception,err:
        logger.warn(err)
    
    fi.close()

class  Ping(object):
    def __init__(self, hosts):
        loss_pat='0 received'
        msg_pat='icmp_seq=1 '
        for host in hosts:
        #for host in hosts.iterkeys():
            jline=0
            count=0
            status=0
            newflg=True
            
            for attr in HISTjson:
                jsonhostname = attr.get('address')
                if host.decode('utf-8') == jsonhostname :
                    newflg=False
                    status = attr.get('status')
                    count = attr.get('count')
                    outjson = attr
                    break
                else :
                    newflg=True

                jline+=1

            ping = subprocess.Popen(
                ["ping","-c","2", "-w","5", host],
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE
            )
            out, error = ping.communicate()

            msg = ''
            for line in out.splitlines():
                if line.find(msg_pat)>-1:
                    msg = line.split(msg_pat)[1]     # エラーメッセージの抽出

                if line.find(loss_pat)>-1:           # パケット未到着ログの抽出
                    errflag=True
                    break
                else:
                    errflag=False                    # breakしなかった場合 = パケットは到着している
            
            #エラー時
            if errflag:
                #新規
                if newflg:
                    outjson = ({"address":host,"status":-1,"count":1})
                else:

                    #発生時
                    #２回目以降
                    outjson['count'] = count+1
                    outjson['status'] = -1
                    
                if count+1 == ERRORCOUNT :
                    REPAIRflg = False
                    #タイムスタンプの30分後の時間を取得
                    ret = changeWaitIntervalChk()
                    if ret == True :
                        sendTrap(host,REPAIRflg)

                logger.warn('[NG]: ' + 'ServerName->' + host + ', Msg->\'' + msg + '\'')
                
                
            #正常時
            else:
                #新規
                if newflg:

                    outjson = {"address":host,"status":1,"count":0}
                else:
                    #復旧
                    if outjson['status'] == -1 :
                        #復旧
                        outjson['count'] = 0
                        outjson['status'] = 1
                        REPAIRflg = True
                        
                        logger.warn('[復旧]: ' + 'ServerName->' + host)

                        #タイムスタンプの30分後の時間を取得
                        ret = changeWaitIntervalChk()
                        if ret == True :
                            sendTrap(host,REPAIRflg)
                    else:
                        #２回目以降
                        HISTjson[jline]['count'] = 0
                        
            filejson.append(outjson)
            
        #ファイルに書き込み
        ft = open(JSONFile, 'w') 
        json.dump(filejson, ft,ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
        ft.close()

def  sendTrap(host,REPAIRflg):
     
    if REPAIRflg :
        #復旧
        cmd = "snmptrap -v 1 -c public %s .1.3.6.1.4.1.119.1.212.2.2.4 %s 6 10 '' .1.3.6.1.4.1.119.1.212.2.2.4.1 i 0" % (TRAPSERVER,host)
        logger.warn('[復旧] トラップを送信しました。 ' + 'ServerName->' + host)
    else:
        #障害
        cmd = "snmptrap -v 1 -c public %s .1.3.6.1.4.1.119.1.212.2.2.4 %s 6 10 '' .1.3.6.1.4.1.119.1.212.2.2.4.1 i 1" % (TRAPSERVER,host)
        logger.warn('[障害] トラップを送信しました。 ' + 'ServerName->' + host)

    snmptrp = subprocess.Popen ( cmd.strip().split(" "),stderr=subprocess.PIPE, stdout=subprocess.PIPE )
    logger.warn(snmptrp.communicate() )

def changeWaitIntervalChk() :
    #タイムスタンプの30分後の時間を取得
    sysproUtime = datetime.datetime.fromtimestamp(os.stat(SYSTEMFILE_PATH).st_mtime) + datetime.timedelta(minutes = 30)
    nowtm = datetime.datetime.now()
    print (sysproUtime)
    #時間を比較し30分以上経過していなかったらフラグFALSEを返す
    delta=nowtm - sysproUtime 
    if delta.days == -1 :
        logger.warn('切り替え直後はトラップを発信しません')
        return False
    return True    
if __name__ == '__main__':

    #hosts=map(lambda x:'xxx.xxx.xxx.'+str(x),range(1,255))
    #hosts= ['192.168.12.5','192.168.12.100'];
    #hosts = {"192.168.12.5":0}

    #現用待機のチェック
    cmd='grep system.Primary ' + SYSTEMFILE_PATH + ' | cut -d "=" -f 2'
    actsby = subprocess.Popen ( cmd,shell = True, stderr=subprocess.PIPE, stdout=subprocess.PIPE )
    out, error = actsby.communicate()

    #ACT 現用  SBY 待機
    if out.strip() == 'SBY' :
        sys.exit()
       
    #ファイルを読み込む
    f = open(IP_LIST_FILE)
    hosts = f.read().strip().split("\n") # 1行毎にファイル終端まで全て読む(改行文字も含まれる)
    f.close()
    #print (hosts)
    
    Ping(hosts)
