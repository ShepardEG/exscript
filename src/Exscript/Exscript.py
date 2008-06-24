import sys, time, os, re, signal, gc, copy, socket, getpass
from Interpreter     import Parser
from FooLib          import UrlParser
from SpiffWorkQueue  import WorkQueue
from SpiffWorkQueue  import Sequence
from TerminalActions import *

True  = 1
False = 0

class Exscript(object):
    """
    This is a half-assed, poorly designed quickhack API for accessing all of 
    Exscript's functions programmatically. One day it'll be cleaned up, so 
    don't count on API stability.
    """
    def __init__(self, **kwargs):
        self.parser         = Parser(**kwargs)
        self.workqueue      = WorkQueue()
        self.exscript       = None
        self.exscript_code  = None
        self.hostnames      = []
        self.host_defines   = {}
        self.global_defines = {}
        self.logdir         = kwargs.get('logdir')


    def add_hosts(self, hosts):
        """
        Adds the given list of hosts for executing the script later.
        """
        self.hostnames += hosts
        for host in hosts:
            query = UrlParser.parse_url(host)[4]
            self.host_defines[host] = query


    def add_hosts_from_file(self, filename):
        """
        Reads a list of hostnames from the file with the given name.
        """
        # Open the file.
        if not os.path.exists(filename):
            raise IOError('No such file: %s' % filename)
        file = open(filename, 'r')

        # Read the hostnames.
        for line in file:
            hostname = line.strip()
            if hostname == '':
                continue
            self.add_hosts([hostname])

        file.close()


    def add_hosts_from_csv(self, filename):
        """
        Reads a list of hostnames and variables from the .csv file with the 
        given name.
        """
        # Open the file.
        if not os.path.exists(filename):
            raise IOError('No such file: %s' % filename)
        file = open(filename, 'r')

        # Read the header.
        header = file.readline().rstrip()
        if re.search(r'^hostname\b', header) is None:
            msg  = 'Syntax error in CSV file header:'
            msg += ' File does not start with "hostname".'
            raise Exception(msg)
        if re.search(r'^hostname(?:\t[^\t]+)*$', header) is None:
            msg  = 'Syntax error in CSV file header:'
            msg += ' Make sure to separate columns by tabs.'
            raise Exception(msg)
        varnames = header.split('\t')
        varnames.pop(0)
        
        # Walk through all lines and create a map that maps hostname to definitions.
        last_hostname = ''
        for line in file:
            line         = re.sub(r'[\r\n]*$', '', line)
            values       = line.split('\t')
            hostname_url = values.pop(0).strip()
            hostname     = UrlParser.parse_url(hostname)[3]

            # Add the hostname to our list.
            if hostname != last_hostname:
                #print "Reading hostname", hostname, "from csv."
                self.add_hosts([hostname_url])
                last_hostname = hostname

            # Define variables according to the definition.
            for i in range(0, len(varnames)):
                varname = varnames[i]
                try:
                    value = values[i]
                except:
                    value = ''
                if self.host_defines[hostname].has_key(varname):
                    self.host_defines[hostname][varname].append(value)
                else:
                    self.host_defines[hostname][varname] = [value]

        file.close()


    def define(self, **kwargs):
        """
        Defines the given variables such that they may be accessed from 
        within the Exscript.
        """
        self.global_defines.update(kwargs)


    def load(self, exscript_content, **kwargs):
        """
        Loads the given Exscript code, using the given options.
        MUST be called before run() is called.

        kwargs: verbose: The verbosity level of the parser.
                no-prompt: Whether the compiled program should wait for a 
                           prompt each time after the Exscript sent a 
                           command to the remote host.
        """
        # Parse the exscript.
        self.parser.define(**self.global_defines)
        self.parser.define(**self.host_defines[self.hostnames[0]])
        self.parser.define(hostname = self.hostnames[0])
        try:
            self.exscript      = self.parser.parse(exscript_content)
	    self.exscript_code = exscript_content
        except Exception, e:
            if kwargs['verbose'] > 0:
                raise
            print e
            sys.exit(1)


    def load_from_file(self, filename, **kwargs):
        """
        Loads the Exscript file with the given name, and calls load() to 
        process the code using the given options.

        kwargs: verbose: The verbosity level of the parser.
                no-prompt: Whether the compiled program should wait for a 
                           prompt each time after the Exscript sent a 
                           command to the remote host.
        """
        file = open(filename, 'r')
        exscript_content = file.read()
        file.close()
        self.load(exscript_content, **kwargs)


    def _run(self, **kwargs):
        """
        Executes the currently loaded Exscript file on the currently added 
        hosts.
        """
        if self.exscript is None:
            msg = 'An Exscript was not yet loaded using load().'
            raise Exception(msg)

        # Initialize the workqueue.
        n_connections = kwargs.get('connections', 1)
        self.workqueue.set_max_threads(n_connections)
        self.workqueue.set_debug(kwargs.get('verbose', 0))

        print 'Starting engine...'
        self.workqueue.start()
        print 'Engine running.'

        # Build the action sequence.
        print 'Building sequence...'
        user      = kwargs.get('user')
        password  = kwargs.get('password')
        password2 = kwargs.get('password2')
        for hostname in self.hostnames:
            # To save memory, limit the number of parsed (=in-memory) items.
            while self.workqueue.get_length() > n_connections * 2:
                time.sleep(1)
                gc.collect()

            if kwargs.get('verbose', 0) > 0:
                print 'Building sequence for %s.' % hostname

            # Prepare variables that are passed to the exscript interpreter.
            default_protocol = kwargs.get('protocol', 'telnet')
            (this_proto,
             this_user,
             this_pass,
             this_host,
             this_query) = UrlParser.parse_url(hostname, default_protocol)
            variables             = self.host_defines[hostname]
            variables['hostname'] = this_host
            variables.update(this_query)
            if this_user is None:
                this_user = user
                this_pass = password

            #FIXME: In Python > 2.2 we can (hopefully) deep copy the object instead of
            # recompiling numerous times.
            exscript = self.parser.parse(self.exscript_code)
            #exscript = copy.deepcopy(self.exscript)
            exscript.init(**variables)

            # One logfile per host.
            logfile       = None
            error_logfile = None
            if self.logdir is None:
                sequence = Sequence(name = this_host)
            else:
                logfile       = os.path.join(self.logdir, this_host + '.log')
                error_logfile = logfile + '.error'
                sequence      = LoggedSequence(name          = this_host,
                                               logfile       = logfile,
                                               error_logfile = error_logfile)

            # Choose the protocol.
            if this_proto == 'telnet':
                protocol = __import__('termconnect.Telnet',
                                      globals(),
                                      locals(),
                                      'Telnet')
            elif this_proto == 'ssh':
                protocol = __import__('termconnect.SSH',
                                      globals(),
                                      locals(),
                                      'SSH')
            else:
                print 'Unsupported protocol %s' % this_proto
                continue

            # Build the sequence.
            noecho       = kwargs.get('no-echo',           False)
            key          = kwargs.get('ssh-key',           None)
            av           = kwargs.get('ssh-auto-verify',   None)
            nip          = kwargs.get('no-initial-prompt', False)
            nop          = kwargs.get('no-prompt',         False)
            authenticate = not kwargs.get('no-authentication', False)
            authorize    = kwargs.get('authorize', False)
            echo         = n_connections == 1 and not noecho
            wait         = not nip and not nop
            sequence.add(Connect(protocol, this_host, echo = echo, auto_verify = av))
            if key is None and authenticate:
                sequence.add(Authenticate(this_user, password = this_pass, wait = wait))
            elif authenticate:
                sequence.add(Authenticate(this_user, key_file = key,       wait = wait))
            if authorize:
                sequence.add(Authorize(password2, wait))
            if kwargs.get('authorize2', False):
                sequence.add(Authorize(this_pass, wait))
            sequence.add(CommandScript(exscript))
            sequence.add(Close())
            self.workqueue.enqueue(sequence)

        # Wait until the engine is finished.
        print 'All actions enqueued.'
        while self.workqueue.get_length() > 0:
            #print '%s jobs left, waiting.' % workqueue.get_length()
            time.sleep(1)
            gc.collect()
        print 'Shutting down engine...'


    def run(self, **kwargs):
        """
        Executes the currently loaded Exscript file on the currently added 
        hosts. Allows for interrupting with SIGINT.
        """
        # Make sure that we shut down properly even when SIGINT or SIGTERM is sent.
        def on_posix_signal(signum, frame):
            print '************ SIGINT RECEIVED - SHUTTING DOWN! ************'
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT,  on_posix_signal)
        signal.signal(signal.SIGTERM, on_posix_signal)

        try:
            self._run(**kwargs)
        except KeyboardInterrupt:
            print 'Interrupt caught succcessfully.'
            print '%s unfinished jobs.' % self.workqueue.get_length()
            sys.exit(1)

        self.workqueue.shutdown()
        print 'Engine shut down.'