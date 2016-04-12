from pygerrit.ssh import GerritSSHClient
import json
import argparse
import logging
import sys

parser = argparse.ArgumentParser(description='Gerrit topics helper')
parser.add_argument('-r', '--reviewers', nargs='+', help='specifies the reviewers to add to the patches')
parser.add_argument('-v', '--verbose', action='store_true', help='execute with extensive logging')
parser.add_argument('-cr', '--code-review', dest='codeReview', help='code review to apply')
parser.add_argument('-vr', '--verified', dest='verified', help='verified review to apply')
parser.add_argument('-lb', '--local-branch', dest='localBranch', help='perform the operation on a local branch')
parser.set_defaults(abandon=False)
subparsers = parser.add_subparsers(help='sub-command help')

gerrit_topic_parser = subparsers.add_parser('gerrit-topic', help='Gerrit topics')
gerrit_topic_parser.add_argument('-t','--topics', nargs='+', help='topics to perform on', required=True)
gerrit_topic_parser.add_argument('-o', '--owners', nargs='+', help='specifies the owners of the patches', required=True)
gerrit_topic_parser.add_argument('-pr', '--projects', nargs='+', help='specifies the projects', required=True)
gerrit_topic_parser.add_argument('-a', '--abandon',  dest='abandon', help='abandon the topic patches')
gerrit_topic_parser.add_argument('-d', '--delete-drafts',  dest='deleteDrafts', help='delete draft changes')

current_branch_parser = subparsers.add_parser('current-branch', help='Current branch')
gerrit_topic_parser.add_argument('-p', '--path',  dest='path', help='path', required=True)

args = parser.parse_args()
d = vars(args)

log = logging.getLogger('Gerrit-topic-helper')
log.setLevel(logging.INFO)
sl = logging.StreamHandler(sys.stdout)
sl.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s::%(levelname)s::%(message)s')
sl.setFormatter(formatter)
log.addHandler(sl)
if d["verbose"]:
	log.setLevel(logging.DEBUG)

def safeGet(key, d):
        if key in d:
                return d[key]
        return None

def applyProp(d, query, prop, arg, sep):
	p = safeGet(arg, d)
        if p is not None:
        	tmp = sep.join(p)

        query+=" {}:{} ".format(prop, tmp)
        return query

def applyOrProp(d, query, prop, arg):
	return applyProp(d, query, prop, arg, " OR ")


client = GerritSSHClient("gerrit.ovirt.org")

def run_gerrit_command(command):
        try:
                return client.run_gerrit_command(command)
        except Exception as e:
                print 'Error when running gerrit command:', e

def get_topic_changes(d):
	query = "query --format=JSON status:open --current-patch-set"
	query = applyOrProp(d, query, "owner", "owners")
	query = applyOrProp(d, query, "topic", "topics")
	query = applyOrProp(d, query, "project", "projects")
	log.info("Running query %s", query)
	query_result = run_gerrit_command(query)
	result = query_result.stdout.readlines()
	return result[:-1]

data = get_topic_changes(d)

reviewers = safeGet("reviewers", d)
code_review = safeGet("codeReview", d)
verified = safeGet("verified", d)

def get_topic_commits(data):
	result = []
	for line in data:
		parsed=json.loads(line)
		commit=parsed["currentPatchSet"]["revision"]
		result += [commit]

	return result

def get_branch_commits(data):
	command = 'git log --format="%H"'
	subprocess.run(["git log ", "-l", "/dev/null"], stdout=subprocess.PIPE)
	result = []
	for line in data:
		parsed=json.loads(line)
		commit=parsed["currentPatchSet"]["revision"]
		result += [commit]

	return result

commits = get_topic_commits(data)

for commit in commits:
	if reviewers is not None:
		reviewers_com = "set-reviewers {} --add ".format(commit)
		reviewers_com+="--add ".join(reviewers)
		log.debug("adding reviewers using command %s", reviewers_com)
		run_gerrit_command(client, reviewers_com)

	review_com = "review"
	if code_review:
		review_com+=" --code-review {} {}".format(code_review, commit)

	if verified:
		review_com+=" --verified {} {}".format(verified, commit)

	deleteDrafts = safeGet("deleteDrafts", d)
	abandon = safeGet("abandon", d)
	if deleteDrafts or abandon:
		if parsed["status"]=="DRAFT":
			if deleteDrafts:
				log.debug("deleting draft commit %s", commit)
				review_com.append(" --delete {}".format(commit))
				continue
			log.debug("publishing draft commit %s", commit)
			review_com+=" --publish {}".format(commit)
		if abandon:
			log.debug("abandoning %s", commit)
			review_com+=" --abandon {}".format(commit)
	log.debug("running git review command %s", review_com)
	client.run_gerrit_command(review_com)
