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
        self.dv_ext = '.dv'

        self.logdir = os.path.join(os.getenv("HOME"),
                                   'SparkleShare/seminar_recording_logs')
        if not os.path.exists(self.logdir):
            self.logdir = '.'

        stime = self.iso_time()
        logname = '-'.join([socket.gethostname(), stime]) + '.log'
        self.logfilename = os.path.join(self.logdir, logname)
        self.loglines = []
        self.potential_webcams = ['DV', 'video4', 'video3', 'video2', 'video1', 'video0']

    def iso_time(self):
        '''
        return ISO time suited for path  
        '''
        stime = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S') #pylint: disable=E1101
        return stime

    def print_status_line(self):
        '''
        Print log line, using state of recording files. 
        ''' 
        stime = self.iso_time()
        terms = [stime, '> ']
        dvsize = 'NA'
        mru_dv_file = self.get_mru_file4ext('-dv')
        if mru_dv_file and os.path.exists(mru_dv_file):
            dvsize = str(os.stat(mru_dv_file).st_size/1024/1024) + 'M'
            terms += ['DV=', dvsize, '    ']
            if 'DV' in self.filesize:
                if self.filesize['DV'] == dvsize:
                    self.webcamgrabbers['DV'].shutdown()
                    dvsize = '---'
                    time.sleep(3)
            self.filesize['DV'] = dvsize
        for video in self.webcamgrabbers:
            webcamsize = 'NA'
            fname = self.webcamgrabbers[video].filename
            if os.path.exists(fname):
                webcamsize = str(os.stat(fname).st_size/1024/1024) + 'M'
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



    def get_duration(self, filename):
        """
        Measure length of audio or movie file using ``ffmpeg``.
        """
        scmd = 'ffmpeg -i "' + filename + '"'
        progin, progout = os.popen4(scmd)
        self.info = progout.read()

        print self.info
        progin.close()
        progout.close()

        reg = re.compile(
            r"(?sm)Duration: (?P<duration>(?P<hours>\d\d):(?P<minutes>\d\d):(?P<seconds>\d\d.?\d?\d?)),"
                        )
        m = reg.search(self.info)
        if m:
            duration = m.group("duration")
            return duration
        return None

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
        if video == 'DV':
            return self.start_firewire_record()
        videodevname = r'/dev/' + video
        if os.path.exists(videodevname):
            scmd =( 'ffmpeg -f video4linux2 -list_formats all '
                    ' -i %(videodevname)s   ' % vars() )
            sres = self.get_out_from_cmd(scmd)
            if not 'mjpeg' in sres:
                return

            stime = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
            webcamfilename = "-".join([stime, video]) + '.avi'
            scmd =( 'ffmpeg -y '
                    ' -f alsa  -i default -itsoffset 00:00:00 '
                    ' -f video4linux2 '
                    ' -input_format mjpeg '
                    ' -s 1280x720 '
                    ' -i %(videodevname)s   '
                    ' -c copy '
                    ' %(webcamfilename)s  ' % vars() )

            scmd =( 'gst-launch-1.0  '
                    " v4l2src device=%(videodevname)s do-timestamp=1 num-buffers=150000 ! "
                    " 'image/jpeg,width=1280,framerate=10/1,rate=10' ! "
                    " stamp sync-margin=2 sync-interval=5 ! queue ! "
                    " avimux name=mux  "
                    " pulsesrc ! audioconvert ! lamemp3enc target=bitrate bitrate=192 cbr=true ! mux. mux. "
                    " ! filesink location=%(webcamfilename)s "
                    % vars() )
            
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


    def start_firewire_record(self):
        def get_firewire_filename():
            stime = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
            faviname = "-".join([stime, 'dv']) + self.dv_ext
            firstchunkname = "-".join([stime, 'dv001']) + self.dv_ext
            return faviname, firstchunkname
            pass

        self.dv_ext = '.m2t'
        fname, firstchunkname = get_firewire_filename()
        scmd = "dvgrab -buffers 300 -noavc -a -size 12000 -f hdv " + fname

        slog = open("dvgrab.log", "w")
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

        time.sleep(1)
        if not file_is_ok(firstchunkname):
            try:
                os.kill(process_.pid, signal.SIGINT)
            except:
                pass

            self.dv_ext = '.dv'
            fname, firstchunkname = get_firewire_filename()
            scmd = "dvgrab -buffers 500 -noavc -a -size 24000 " + fname

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
            ptran = None
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
    try:
        semrec.start_recording(recordpath)
    finally:
        semrec.shutdown_webcams()
        os.killpg(0, signal.SIGKILL) 


if __name__ == '__main__':
    main()
