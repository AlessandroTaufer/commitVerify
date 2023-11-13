import subprocess
import re
import logging
import argparse
import json
import os


# Returns the sha1 related to all the commits that the child has in history and the parent has not
# E.g. returns the list of sha1 added in the pr
def get_pr_commit_list(child_branch, parent_branch, git_folder):
    cmd = ['git', '-C', git_folder, 'log', child_branch, f"^{parent_branch}", '--format=format:%H']
    commits = subprocess.check_output(cmd).decode().split('\n')
    return commits


# Given a list of commits and the git folder, returns the  gpg signature's metadata
def get_signature_metadata_from_commit(commits, git_folder):
    for commit_sha1 in commits:
        cmd = ['git', '-C', git_folder, 'verify-commit', commit_sha1]
        # cmd = ['git', '-C', git_folder, 'log']
        print(" ".join(cmd))

        verify_command = subprocess.run(cmd, stderr=subprocess.PIPE)

        # If the git commit hasn't been signed the return code will be 1
        if verify_command.returncode != 0:
            # TODO use fstrings
            logging.error(f"The following commit couldn't be verified - " + str(commit_sha1))
            logging.debug(f"Return code:" + str(verify_command.returncode))
            logging.debug(verify_command.stderr)
            return False

        # The command output containing the gpg metadata is printed on stderr
        verify_command_output = verify_command.stderr.decode()

        # The gpg metadata is extracted from the output
        gpg_metadata = extract_signature_metadata_from_output(verify_command_output, commit_sha1)
        logging.debug('Commit metadata - ' + commit_sha1)
        logging.debug(gpg_metadata)

        return gpg_metadata


# Given a commit metadata, checks if it satisfies the requirements
# Checks that every commit in the branch has been signed by a trusted contributor
def validate_branch(commits_signature_metadata, contributors):
    for commit in commits_signature_metadata:
        for contributor in contributors:
            if validate_gpg_metadata(contributor, commit):
                logging.debug('The commit is successfully signed by')

                # Move the contributor on top of the list to speed up the future validations
                # In fact, if somebody contributed once it has a higher probability to have more than one commits
                contributors.remove(contributor)
                contributors.insert(0, contributor)
                return True
    return False


# Given a contributor and a commit_gpg_metadata checks if all the fields match. If the match returns the contributor
def validate_gpg_metadata(contributor, gpg_metadata):
    if gpg_metadata['gpg_public_key'] == contributor['gpg_public_key']:
        return True
    return False


# Given the stderr of a verify-commit function extracts the gpg metadata
def extract_signature_metadata_from_output(verify_command_output, commit_sha1=None):
    # TODO creating an object wouldn't be so bad, you know?
    metadata = {
        'gpg_data': re.search('Signature made (.*)', verify_command_output).group(1),
        'gpg_public_key': re.search('using RSA key (.*)', verify_command_output).group(1),
        'author': re.search('Good signature from \"(.*) <', verify_command_output).group(1),
        'email': re.search('<(.*@.*)>', verify_command_output).group(1),
        'gpg_signature_type': re.search('\[(.*)]', verify_command_output).group(1)
    }
    
    if commit_sha1 is not None:
        metadata['commit_sha1'] = commit_sha1

    return metadata


# Returns a dictionary containing all the information related to the contributors that are allowed to commit
def load_contributors_conf(contributors_folder):  # TODO this is stateful, we don't do that here
    contributors = []

    # It will loop through the contributors folder and load all the contributors allowed metadata
    for contributor_file in os.listdir(contributors_folder):
        contributor_conf = json.load(open(os.path.join(contributors_folder, contributor_file)))
        contributors.append(contributor_conf)

    logging.info('Contributors configuration loaded successfully')
    logging.debug(contributors)
    print(contributors)
    return contributors


if __name__ == '__main__':
    # Read the PR_source_branch and PR_destination_branch from the arguments passed during the script execution
    # TODO support a multi-branch build
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(dest='source_branch', help='Source branch of the Pull Request')
    argument_parser.add_argument(dest='destination_branch', help='Destination branch of the Pull Request')
    argument_parser.parse_args()

    # We load the trusted contributors on the repository
    contributors = load_contributors_conf('./contributors')

    git_folder = '/home/alessandro/Documents/BlockchainforGOOD'

    # Extracts all the commmits related to the PR
    # TODO pass the arguments as parameters
    commits = get_pr_commit_list('add_readme', 'main', git_folder)

    # For each commit check that it's signed and extract the signature metadata
    commit_signatures = [get_signature_metadata_from_commit(commits, git_folder) for commit in commits]

    # We ensure that the branch is safe by checking if every commit_signature belongs to a trusted contributor
    is_branch_valid = validate_branch(commit_signatures, contributors)

    if is_branch_valid:
        logging.info('The given branch has been successfully validated')
        print("The branch is valid")
        exit(0)
    else:
        logging.warning('The given branch contains at least a commit that is not valid')
        print("[!] - The branch is not valid")
        exit(1)