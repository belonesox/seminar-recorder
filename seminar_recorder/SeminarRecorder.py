#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
  Seminar Recorder.
  Record streams from DV, HDV and webcams
"""
import sys
import os
import time
import subprocess
import datetime
import re
import signal
import socket
import belonesox_tools.MiscUtils as ut


def strip_gst_comments(scmd):
    '''
     Remove #comments from multiline GST magic
    ''' 
    scmd = re.sub(r'(?m)^#[^\n]*\n', "", scmd)
    scmd = re.sub(r'(?m)(?P<repl>[^\\])#[^\n]*\n', r'\1\n', scmd)
    scmd = re.sub(r'[\s]+\n', r'\n', scmd  )
    return scmd



class RecordingProcess(object):
    def __init__(self, process, filename):
        '''
          Associate process with filename 
        '''
        self.process = process
        self.filename = filename

    def shutdown(self):
        '''
        Shutdown the process
        '''
        try:
            os.kill(self.process.pid, signal.SIGINT)
        except:
            pass

class SeminarRecorder:
    """
      Record video from several sources.
    """
    def __init__(self):
        """
           Check for input files,
           substitute random defaults for missing audio files.
        """
        os.system('killall ffmpeg')
        os.system('killall dvgrab')

        self.filesize = {}

        #home/working directory
        self.homedir = os.getcwd()
        self.recorddir = None
        self.translated_file = None
        self.webcamgrabbers = None

        self.logdir = os.path.join(os.getenv("HOME"),
                                   'SparkleShare/seminar_recording_logs')
        if not os.path.exists(self.logdir):
            self.logdir = '.'

        stime = self.iso_time()
        logname = '-'.join([socket.gethostname(), stime]) + '.log'
        self.logfilename = os.path.join(self.logdir, logname)
        self.loglines = []
        self.reload_potential_webcams()
        pass
        
        
        
    def reload_potential_webcams(self):
        sout = self.get_out_from_cmd('v4l2-ctl --list-devices')
        lines = sout.split('\n')
        self.potential_webcams  = {}
        self.potential_webcams['DV']  = 'HDV'
        for i in xrange(len(lines)/3):
            name = lines[i*3]
            devvideo = lines[3*i+1].strip().replace(r'/dev/', '')
            if name.find('LifeCam')>0 or name.find('DVC')>=0:
                self.potential_webcams[devvideo] = name
        pass         

    def iso_time(self):
        '''
        return ISO time suited for path  
        '''
        now = datetime.datetime.now()  #pylint: disable=E1101
        millis = now.microsecond/1000
        stime = now.strftime('%Y-%m-%d-%H-%M-%S') + '-' + "%03d" % millis 
        return stime

    def print_status_line(self):
        '''
        Print log line, using state of recording files. 
        ''' 

        def size4file(filename):
            filesize = str(os.stat(filename).st_size/1024/1024) + 'M'
            return filesize
        
        stime = self.iso_time()
        terms = [stime, '> ']
        # dvsize = 'NA'
        # mru_dv_file = self.get_mru_file4ext('-firewire')
        # if mru_dv_file and os.path.exists(mru_dv_file):
        #     dvsize = size4file(mru_dv_file)
        #     terms += ['DV=', dvsize, '    ']
        #     if 'DV' in self.filesize:
        #         if self.filesize['DV'] == dvsize:
        #             self.webcamgrabbers['DV'].shutdown()
        #             dvsize = '---'
        #             time.sleep(3)
        #     self.filesize['DV'] = dvsize
        for video in set(self.webcamgrabbers.keys()).intersection(self.potential_webcams.keys()):
            webcamsize = 'NA'
            fname = self.webcamgrabbers[video].filename
            if self.potential_webcams[video].find('DVC') >= 0:
                fname = self.get_mru_file4ext('-' + video)
            if self.potential_webcams[video].find('HDV') >= 0:
                fname = self.get_mru_file4ext('-firewire')

            if fname and os.path.exists(fname):
                webcamsize = size4file(fname)
                terms += [' %(video)s=' % vars(), webcamsize]
                if video in self.filesize:
                    if self.filesize[video] == webcamsize:
                        self.webcamgrabbers[video].shutdown()
                        webcamsize = '---'
                        time.sleep(3)
            self.filesize[video] = webcamsize

        logline = "".join(terms)
        print logline
        self.loglines = [logline] + self.loglines[:100]
        lf = open(self.logfilename, 'w')
        lf.write('\n'.join(self.loglines))
        lf.close()

    def get_out_from_cmd(self, scmd):
        """
        Get output from command
        """
        progin, progout = os.popen4(scmd)
        sresult =  progout.read()

        progin.close()
        progout.close()

        return sresult

    def get_mru_file4ext(self, suffix):
        avilist = [f for f in os.listdir('.')
               if (suffix in f.lower())]

        timedlist = []
        for f in avilist:
            timedlist.append( (os.stat(f).st_mtime, f) )

        self.mru_file = None

        if not timedlist:
            return

        timedlist.sort()
        timedlist.reverse()
        mru_file = timedlist[0][1]
        return mru_file

    def shutdown_webcams(self):
        for video in self.webcamgrabbers:
            self.webcamgrabbers[video].shutdown()

    def activate_input_sources(self):
        for video in self.potential_webcams:
            if video in self.webcamgrabbers:
                pr = self.webcamgrabbers[video].process.poll()
                if not (pr == None):
                    self.webcamgrabbers[video].shutdown
                    del self.webcamgrabbers[video]
                    self.start_webcam_record(video)
            else:
                self.start_webcam_record(video)

        exist_live = False
        for video in self.webcamgrabbers:
            pr = self.webcamgrabbers[video].process.poll()
            if pr == None:
                exist_live = True
        return exist_live


    def start_webcam_record(self,  video):
        '''
    Actually now hardcoded to Microsoft LifeCam 
        '''    
        if video == 'DV':
            return self.start_firewire_record()
        videodevname = r'/dev/' + video

        if os.path.exists(videodevname):
            webname = self.potential_webcams[video]
            if webname.find('DVC') >= 0:
                return self.start_dvusb_record(video)
            # scmd =( 'ffmpeg -f video4linux2 -list_formats all '
            #         ' -i %(videodevname)s   ' % vars() )
            # sres = self.get_out_from_cmd(scmd)
            # if not 'mjpeg' in sres:
            #     return

            webblock_in_seconds = 60*60
            numbuffersv = webblock_in_seconds*10
            numbuffersa = webblock_in_seconds*100
            audioblock = ' \ '
            sout = self.get_out_from_cmd('arecord -l')
            mre = re.search('card (?P<card>\d+): CinemaTM', sout)
            if mre:
                cardnum = mre.groups('card')[0]
                audioblock = r'''
alsasrc device="hw:%(cardnum)s,0" num-buffers=%(numbuffersa)d   \
  ! queue ! audioconvert ! queue \
 !  mux. \
''' % vars()


            stime = self.iso_time()
            webcamfilename = "-".join([stime, video]) + '.avi'

            gst_code = r'''gst-launch-1.0   \
#    audiotestsrc \
#alsasrc \
#      ! audio/x-raw, rate=16000, channels=1 \
#      ! audioconvert \
#      ! 'audio/x-raw, rate=16000, channels=1' \       
#     ! queue  \
#     ! audioresample \
#     ! audio/x-raw,rate=16000,channels=1 \
#     ! queue  \
#      ! queue max-size-bytes=200000 \
#      !  avimux  name=mux \
       avimux name=mux \
  v4l2src device=%(videodevname)s do-timestamp=1 num-buffers=%(numbuffersv)d \
#  v4l2src device=%(videodevname)s \
#      !  'image/jpeg,width=1280,framerate=10/1,rate=10' \
      !  'image/jpeg, width=1280, framerate=(fraction)10/1'  \
# videotestsrc \
#     ! video/x-raw, framerate=10/1, width=1280, height=720 \
     ! queue max-size-bytes=2000000 \
     !  stamp sync-margin=2 sync-interval=1 \
     ! queue max-size-bytes=2000000 \
     !  mux. \
%(audioblock)s
#     !  fakesink \
    mux. \
     !  filesink location=%(webcamfilename)s \
''' % vars()
            scmd = strip_gst_comments(gst_code) % vars()
            print scmd

            playtest = '''
gst-launch-1.0   \
  v4l2src device=/dev/video0 do-timestamp=1 num-buffers=3000 \
      !  'image/jpeg, width=1280, framerate=(fraction)10/1'  \
     ! queue max-size-bytes=2000000 \
     !  stamp sync-margin=2 sync-interval=1 \
     ! queue max-size-bytes=2000000 \
      !  avimux  name=mux \
        alsasrc device="hw:3,0" num-buffers=30000  \
      ! queue ! audioconvert ! queue \
     !  mux. \
    mux. \
     !  filesink location=test-mjpeg-with-audio.avi
'''
            
            #gst-launch-1.0   v4l2src device=/dev/video0 !  'image/jpeg,width=1280,framerate=10/1,rate=10' ! avimux ! filesink location=2014-10-16-17-10-53-video0.avi 

            slog = open("webcamlog-%(video)s.log" % vars(), "w")
            print scmd
            pid = subprocess.Popen(scmd, shell=True, stderr=slog)
            rp = RecordingProcess(pid, webcamfilename)
            self.webcamgrabbers[video] = rp
            slog.close()
            #time.sleep(5)
            absfilename = os.path.realpath(webcamfilename)
            print absfilename
            scmd = 'ffplay -ss 24:00:00 -r 1 %(absfilename)s' % vars()
            print scmd
            #break
        pass


    def start_dvusb_record(self, video):
        def get_firewire_filename():
            stime = self.iso_time()
            faviname = "-".join([stime, video]) + '.dv'
            firstchunkname = "-".join([stime, 'dv001']) + '.dv'
            return faviname, firstchunkname
            pass

        fname, firstchunkname = get_firewire_filename()
        scmd = "dvgrab -V -buffers 300 -noavc -a -size 24000 -V -input /dev/%(video)s  " % vars() + fname

        slog = open("dvgrab-%(video)s.log" % vars(), "w")
        process_ = subprocess.Popen(scmd, shell=True, stdout=slog)
        slog.close()

        def file_is_ok(fname):
            '''
            If file exists and non empty
            '''
            if not os.path.exists(fname):
                return False
            if os.stat(fname).st_size == 0:
                return False
            return True

        self.webcamgrabbers[video] = RecordingProcess(process_, fname)

    def start_firewire_record(self):
        '''
        Start 
        '''
        def get_firewire_filename():
            stime = self.iso_time()
            fname = "-".join([stime, 'firewire-']) 
            #firstchunkname = "-".join([stime, 'dv001']) + self.dv_ext
            return fname
            pass

        fname = get_firewire_filename()
        scmd = "dvgrab -buffers 600 -a -size 48000  " + fname

        slog = open("dvgrab.log", "w")
        process_ = subprocess.Popen(scmd, shell=True, stdout=slog)
        slog.close()

        self.webcamgrabbers['DV'] = RecordingProcess(process_, fname)


    def start_recording(self, recordpath):
        """
         Fork tools for recording screen and sound with given parameters.
         Kill both then one of them are ends up.
        """
        def directory_ok(thedir):
            if not os.path.exists(thedir):
                try:
                    ut.createdir(thedir)
                except:
                    pass
                if os.path.exists(thedir):
                    return True
                return False
            else:
                testdir = os.path.join(thedir, '~~test-for-recording')
                try:
                    ut.createdir(testdir)
                except:
                    pass
                if os.path.exists(testdir):
                    ut.removedirorfile(testdir)
                    return True
            return False

        homedir = os.getcwd()

        if not directory_ok(recordpath):
            print 'Cannot create directory for recording, call Stas Fomin!'
            sys.exit(0)

        stime = self.iso_time()
        os.chdir(recordpath)
        recorddir = "-".join([stime, r"recording"])
        recorddir = os.path.realpath(recorddir)
        if not os.path.exists(recorddir):
            os.mkdir(recorddir)
        self.recorddir = os.path.realpath(recorddir)
        os.chdir(recorddir)

        self.webcamgrabbers = {}

        try:
            while True:
                self.activate_input_sources()
                self.print_status_line()
                time.sleep(10)
            pass

        except KeyboardInterrupt:
            pass
            print 'Keyboard INT'
        self.shutdown_webcams()
        print "Recording stopped!"
        os.chdir(homedir)

def main():
    '''
    Start recording from all available sources.
    '''
    recordpath = 'avifiles'
    if len(sys.argv) > 1:
        recordpath = sys.argv[1]

    semrec = SeminarRecorder()
    #os.setpgrp()
    try:
        semrec.start_recording(recordpath)
    finally:
        semrec.shutdown_webcams()
        #os.killpg(0, signal.SIGKILL) 


if __name__ == '__main__':
    main()
