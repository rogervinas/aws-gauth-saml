import pychrome
import os
import boto3
import re
from simple_term_menu import TerminalMenu


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
    def __init__(self, account_name, account_id, account_role_name):
        self.account_name = account_name
        self.account_id = account_id
        self.account_role_name = account_role_name
        self.display_name = f'{self.account_name} ({self.account_id}) - {self.account_role_name}'


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
                    account_role_node_ids = self.parser.query_selector_all(account_node_id,
                                                                           'div .saml-role-description')
                    for account_role_node_id in account_role_node_ids:
                        account_role_name = self.parser.get_outer_html(account_role_node_id + 1)
                        accounts.append(AWSAccount(account_name, account_id, account_role_name))
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
    def __aws_assume_role_with_saml(self, aws_account_id, aws_role, saml):
        print(f'Assuming role {aws_role} ...')
        aws_role_arn = f'arn:aws:iam::{aws_account_id}:role/{aws_role}'
        aws_principal_arn = f'arn:aws:iam::{aws_account_id}:saml-provider/g'
        client = boto3.client('sts')
        response = client.assume_role_with_saml(
            RoleArn=aws_role_arn,
            PrincipalArn=aws_principal_arn,
            SAMLAssertion=saml
        )
        return response['Credentials']

    def __aws_configure_profile(self, aws_account):
        print(f'Configuring profile for {aws_account} ...')
        aws_region = os.popen(f'aws configure get region --profile "{aws_account}" 2> /dev/null | tr -d "\n"').read()
        if len(aws_region) == 0:
            print(f'Please select region for {aws_account}:')
            aws_region = choose_region()
            os.system(f'aws configure set region "{aws_region}" --profile "{aws_account}"')

    def __aws_configure_credentials(self, aws_account, creds):
        print(f'Configuring credentials for {aws_account} ...')
        os.system(f'aws configure set aws_access_key_id "{creds["AccessKeyId"]}" --profile "{aws_account}"')
        os.system(f'aws configure set aws_secret_access_key "{creds["SecretAccessKey"]}" --profile "{aws_account}"')
        os.system(f'aws configure set aws_session_token "{creds["SessionToken"]}" --profile "{aws_account}"')

    def __aws_export_profile(self, aws_account):
        export_aws_profile = f'export AWS_PROFILE={aws_account}'
        copy_to_clipboard(export_aws_profile)
        print(f'Set default profile with (already copied to clipboard):\n\n{export_aws_profile}\n')

    def configure(self, aws_account, aws_account_id, aws_role, saml):
        self.__aws_configure_profile(aws_account)
        creds = self.__aws_assume_role_with_saml(aws_account_id, aws_role, saml)
        self.__aws_configure_credentials(aws_account, creds)
        self.__aws_export_profile(aws_account)


def copy_to_clipboard(value):
    os.system(f'echo {value} | tr -d "\n" | pbcopy')


def choose_region():
    options = [
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
    selected = TerminalMenu(options).show()
    return options[selected]


def choose_account(aws_accounts):
    options = map(lambda account: account.display_name, aws_accounts.accounts)
    selected = TerminalMenu(options).show()
    return aws_accounts.accounts[selected]


def unset_aws_variables():
    os.environ.pop('AWS_PROFILE', None)
    os.environ.pop('AWS_DEFAULT_PROFILE', None)


def main():
    unset_aws_variables()
    aws_accounts = AWSAccountsCapturer().get_accounts()
    aws_account = choose_account(aws_accounts)
    AWSConfigurer().configure(
        aws_account=aws_account.account_name,
        aws_account_id=aws_account.account_id,
        aws_role=aws_account.account_role_name,
        saml=aws_accounts.saml_response
    )


if __name__ == '__main__':
    main()
