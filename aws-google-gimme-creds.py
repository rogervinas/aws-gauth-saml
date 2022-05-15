import pychrome
import os
import boto3
import re
from simple_term_menu import TerminalMenu
import argparse


class SubstringMatcher:
    def __init__(self, substring=None):
        self.__substring = substring

    def matches(self, string):
        return self.__substring is None or self.__substring in string


class DOMParser:
    def __init__(self, tab):
        self.tab = tab
        self.root_node_id = self.tab.call_method("DOM.getDocument", depth=1)['root']['nodeId']

    def query_selector(self, node_id, selector):
        return self.tab.call_method("DOM.querySelector", nodeId=node_id, selector=selector)['nodeId']

    def query_selector_all(self, node_id, selector):
        return self.tab.call_method("DOM.querySelectorAll", nodeId=node_id, selector=selector)['nodeIds']

    def get_attributes(self, node_id):
        attributes = iter(self.tab.call_method("DOM.getAttributes", nodeId=node_id)['attributes'])
        return dict(zip(attributes, attributes))

    def get_outer_html(self, node_id):
        return self.tab.call_method("DOM.getOuterHTML", nodeId=node_id)['outerHTML']


class AWSAccounts:
    def __init__(self, accounts, saml_response):
        self.accounts = accounts
        self.saml_response = saml_response


class AWSAccount:
    def __init__(self, account_name, account_id, role_name):
        self.account_name = account_name
        self.account_id = account_id
        self.role_name = role_name
        self.display_name = f'{self.account_name} ({self.account_id}) - {self.role_name}'


class AWSAccountsDOMParser:
    def __init__(self, tab):
        self.parser = DOMParser(tab)

    def __parse_account_label(self, account_label):
        account_label_matcher = re.search(r'Account: (.+) \((\d+)\)', account_label)
        if account_label_matcher is not None:
            return [account_label_matcher.group(1), account_label_matcher.group(2)]
        else:
            return [None, None]

    def __get_saml(self):
        saml_response_node_id = self.parser.query_selector(self.parser.root_node_id, 'input[name="SAMLResponse"]')
        saml_response = self.parser.get_attributes(saml_response_node_id)['value']
        return saml_response

    def __get_accounts(self):
        accounts = []
        account_node_ids = self.parser.query_selector_all(self.parser.root_node_id, 'div .saml-account')
        for account_node_id in account_node_ids:
            account_label_node_id = self.parser.query_selector(account_node_id, 'div .saml-account-name')
            if account_label_node_id != 0:
                account_label = self.parser.get_outer_html(account_label_node_id + 1)
                account_name, account_id = self.__parse_account_label(account_label)
                if account_name is not None and account_id is not None:
                    role_node_ids = self.parser.query_selector_all(account_node_id, 'div .saml-role-description')
                    for role_node_id in role_node_ids:
                        role_name = self.parser.get_outer_html(role_node_id + 1)
                        accounts.append(AWSAccount(account_name, account_id, role_name))
        return accounts

    def get_accounts(self):
        return AWSAccounts(self.__get_accounts(), self.__get_saml())


class AWSAccountsCapturer:
    def get_accounts(self):
        aws_login_url = os.environ['AWS_LOGIN_URL']
        browser = pychrome.Browser(url="http://127.0.0.1:9222")
        tab = browser.new_tab()
        tab.start()
        tab.Network.enable()
        tab.Page.navigate(url=aws_login_url, _timeout=5)
        tab.wait(1)
        accounts = AWSAccountsDOMParser(tab).get_accounts()
        tab.stop()
        browser.close_tab(tab)
        return accounts


class AWSConfigurer():
    def __aws_assume_role_with_saml(self, account_id, role, saml):
        print(f'Assuming role {role} ...')
        role_arn = f'arn:aws:iam::{account_id}:role/{role}'
        principal_arn = f'arn:aws:iam::{account_id}:saml-provider/g'
        client = boto3.client('sts')
        response = client.assume_role_with_saml(
            RoleArn=role_arn,
            PrincipalArn=principal_arn,
            SAMLAssertion=saml
        )
        return response['Credentials']

    def __aws_configure_profile(self, account, region_matcher):
        region = os.popen(f'aws configure get region --profile "{account}" 2> /dev/null | tr -d "\n"').read()
        if len(region) == 0:
            print(f'Please select region for {account}:')
            region = choose_region(region_matcher)
            if region is not None:
                print(f'Configuring region {region} for {account} ...')
                os.system(f'aws configure set region "{region}" --profile "{account}"')
            else:
                print('WARNING: No region found matching criteria')

    def __aws_configure_credentials(self, account, creds):
        print(f'Configuring credentials for {account} ...')
        os.system(f'aws configure set aws_access_key_id "{creds["AccessKeyId"]}" --profile "{account}"')
        os.system(f'aws configure set aws_secret_access_key "{creds["SecretAccessKey"]}" --profile "{account}"')
        os.system(f'aws configure set aws_session_token "{creds["SessionToken"]}" --profile "{account}"')

    def __aws_export_profile(self, account):
        export_aws_profile = f'export AWS_PROFILE={account}'
        copy_to_clipboard(export_aws_profile)
        print(f'Copied to clipboard: {export_aws_profile}')

    def configure(self, account, account_id, role, saml, region_matcher):
        self.__aws_configure_profile(account, region_matcher)
        creds = self.__aws_assume_role_with_saml(account_id, role, saml)
        self.__aws_configure_credentials(account, creds)
        self.__aws_export_profile(account)


def copy_to_clipboard(value):
    os.system(f'echo {value} | tr -d "\n" | pbcopy')


def choose_option(options, options_to_display=None):
    if len(options) == 0:
        return None
    elif len(options) == 1:
        return options[0]
    else:
        selected = TerminalMenu(options if options_to_display is None else options_to_display).show()
        return options[selected]


def choose_region(region_matcher):
    regions_to_choose = list(filter(
        lambda region: region_matcher.matches(region),
        [
            "us-east-2",
            "us-east-1",
            "us-west-1",
            "us-west-2",
            "af-south-1",
            "ap-east-1",
            "ap-south-1",
            "ap-northeast-3",
            "ap-northeast-2",
            "ap-southeast-1",
            "ap-southeast-2",
            "ap-northeast-1",
            "ca-central-1",
            "cn-north-1",
            "cn-northwest-1",
            "eu-central-1",
            "eu-west-1",
            "eu-west-2",
            "eu-west-3",
            "eu-north-1",
            "eu-south-1",
            "me-south-1",
            "sa-east-1",
            "us-gov-west-1",
            "us-gov-east-1"
        ]
    ))
    return choose_option(regions_to_choose)


def choose_account(accounts, account_matcher, role_matcher):
    accounts_to_choose = list(filter(
        lambda account: account_matcher.matches(account.account_name) and role_matcher.matches(account.role_name),
        accounts.accounts
    ))
    return choose_option(
        accounts_to_choose,
        map(lambda it: it.display_name, accounts_to_choose)
    )


def unset_aws_variables():
    os.environ.pop('AWS_PROFILE', None)
    os.environ.pop('AWS_DEFAULT_PROFILE', None)


def parse_args():
    parser = argparse.ArgumentParser(description='Assume AWS role using Google logins')
    parser.add_argument('-a', '--account', dest='account_matcher', help='Account name substring to match')
    parser.add_argument('-r', '--role', dest='role_matcher', help='Role name substring to match')
    parser.add_argument('-g', '--region', dest='region_matcher', help='Region name substring to match')
    return parser.parse_args()


def main():
    args = parse_args()
    unset_aws_variables()
    accounts = AWSAccountsCapturer().get_accounts()
    account = choose_account(
        accounts,
        account_matcher=SubstringMatcher(args.account_matcher),
        role_matcher=SubstringMatcher(args.role_matcher)
    )
    if account is not None:
        AWSConfigurer().configure(
            account=account.account_name,
            account_id=account.account_id,
            role=account.role_name,
            saml=accounts.saml_response,
            region_matcher=SubstringMatcher(args.region_matcher)
        )
    else:
        print("ERROR: No account/role found matching criteria")


if __name__ == '__main__':
    main()
