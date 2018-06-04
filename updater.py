
import json
import facebook
from virus_total_apis import PrivateApi as VirusTotalPrivateApi
import threatgraph
import time
import datetime

class Updater:

    def __init__(self, probe, probe_time, probe_id):

        self.g = threatgraph.Gaffer()

        self.probe = probe
        self.probe_time = probe_time
        self.probe_id = probe_id

    def update(self):

        # Get list of all things which need to be updated.
        things = self.fetcher(self)
        
        # Iterate over domains
        for thing in things:

            print thing
    
            elts = self.reporter(self, thing)

            # Execute Gaffer insert
            url = "/rest/v2/graph/operations/execute"
            data = json.dumps(elts)
            response = self.g.post(url, data)

            # If status code is bad, fail
            if response.status_code != 200:
                print response.text

            time.sleep(0.01)

class FacebookUpdater(Updater):

    @staticmethod
    def domain_updater():

        probe_time=1
        u = FacebookUpdater("fb-dm-v0", probe_time, "facebook-domain")

        u.fetcher = lambda self: self.g.get_unprobed_domains(self.probe)

        def reporter(self, domain):
            res = self.fb.get_domain_report(domain)
            return self.facebook_threats_to_elts(domain, res["data"])

        u.reporter = reporter

        return u

    @staticmethod
    def ip_updater():

        probe_time=1
        u = FacebookUpdater("fb-ip-v0", probe_time, "facebook-ip")

        u.fetcher = lambda self: self.g.get_unprobed_ips(self.probe)

        def reporter(self, ip):
            res = self.fb.get_ip_report(ip)
            return self.facebook_threats_to_elts(ip, res["data"])

        u.reporter = reporter

        return u

    def __init__(self, probe, probe_time, probe_id):

        Updater.__init__(self, probe, probe_time, probe_id)

        # Blacklist source info
        self.src = "facebook.com"
        self.tp = "blacklist"

        # Get Facebook creds
        creds = json.loads(open("facebook-creds").read())
        self.fb = facebook.Facebook(creds["id"], creds["secret"])

    def facebook_threats_to_elts(self, thing, threats):
    
        # Initialise graph elements
        elts = []

        # Iterate over threat data
        for threat in threats:

            ok = True
            for reac in threat.get("reactions", []):
                if reac["key"] == "NOT_HELPFUL":
                    ok = False

            if ok == False:
                print "Ignoring blacklist, marked NOT HELPFUL"
                continue

            if threat["review_status"] == "UNREVIEWED":
                print "Ignore unreviewed threat"
                continue

            # Blacklist
            blres = self.fb.parse_threat(threat)
            bl, prob, id, desc, status, severity, pub = blres

            # Create a blacklist match edge
            elt = self.g.make_match_edge(thing, bl, id=id, description=desc,
                                         status=status, severity=severity)
            elts.append(elt)

            print "Blacklist = ", bl
            print "Probability = ", prob
            print "Description = ", desc

            # Create a blacklist entity (probably exists already)
            elt = self.g.make_blacklist_entity(bl, prob, self.tp, self.src,
                                               pub)
            elts.append(elt)

        # Create a probed edge
        elt = self.g.make_probed_edge(thing, self.probe_id, self.probe,
                                      self.probe_time)
        elts.append(elt)

        # Turn element list into a Gaffer operation
        elts = {
            "class": "uk.gov.gchq.gaffer.operation.impl.add.AddElements",
            "validate": True,
            "skipInvalidElements": False,
            "input": elts
        }

        return elts

class VirusTotalUpdater(Updater):

    @staticmethod
    def domain_updater():

        probe_time=1
        u = VirusTotalUpdater("vt-dm-v0", probe_time, "virustotal-domain")

        u.fetcher = lambda self: self.g.get_unprobed_domains(self.probe)

        def reporter(self, domain):
            res = self.vt.get_domain_report(domain)
            dets = res.get("results", {}).get("detected_urls", [])
            return self.vt_threats_to_elts(domain, dets)

        u.reporter = reporter

        return u

    @staticmethod
    def ip_updater():

        probe_time=1
        u = VirusTotalUpdater("vt-ip-v0", probe_time, "virustotal-ip")

        u.fetcher = lambda self: self.g.get_unprobed_ips(self.probe)

        def reporter(self, ip):
            res = self.vt.get_ip_report(ip)
            dets = res.get("results", {}).get("detected_urls", [])
            return self.vt_threats_to_elts(ip, dets)

        u.reporter = reporter

        return u

    def __init__(self, probe, probe_time, probe_id):

        Updater.__init__(self, probe, probe_time, probe_id)

        # Blacklist source info
        self.src = "virustotal.com"
        self.pub = "virustotal.com"
        self.tp = "scan"

        # Get VT creds
        api_key = open("virustotal-key").read().lstrip().rstrip()
        self.vt = VirusTotalPrivateApi(api_key)

    def vt_threats_to_elts(self, thing, dets):

        elts = []

        for det in dets:
            print det
            tm = det["scan_date"]
            tm = datetime.datetime.strptime(tm, "%Y-%m-%d %H:%M:%S")
            tm = time.mktime(tm.timetuple())

            # Blacklist name
            bl = "vt." + det["url"]
            prob = 0.1
            id = det["url"]
            desc = "VirusTotal hit on %s" % det["url"]
            
            # Create a blacklist match edge
            elt = self.g.make_match_edge(thing, bl, id=id, description=desc,
                                         time=tm)
            elts.append(elt)

            print "Blacklist = ", bl
            print "Probability = ", prob
            print "Description = ", desc

            # Create a blacklist entity (probably exists already)
            elt = self.g.make_blacklist_entity(bl, prob, self.tp, self.src,
                                               self.pub, time=tm)
            elts.append(elt)

        # Create a probed edge
        elt = self.g.make_probed_edge(thing, self.probe_id, self.probe,
                                      self.probe_time)
        elts.append(elt)

        # Turn element list into a Gaffer operation
        elts = {
            "class": "uk.gov.gchq.gaffer.operation.impl.add.AddElements",
            "validate": True,
            "skipInvalidElements": False,
            "input": elts
        }

        return elts

