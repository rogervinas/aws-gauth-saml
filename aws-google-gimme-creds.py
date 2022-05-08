import pychrome
import re
import urllib.parse
import os
import boto3
import sys


class SAMLCapturer:
    def __init__(self):
        self.__saml = None

    def __request_callback(self, **kwargs):
        request = kwargs.get('request')
        post_data = request.get('postData')
        if post_data is not None:
            post_data = request.get('postData')
            saml_match = re.search(r'SAMLResponse=([^&]+)', post_data)
            if saml_match:
                self.__saml = urllib.parse.unquote(saml_match.group(1))
            else:
                self.__saml = None

    def capture_saml(self):
        print('Capturing SAML ...')
        aws_google_idpid = os.environ['AWS_GOOGLE_IDPID']
        aws_google_spid = os.environ['AWS_GOOGLE_SPID']
        browser = pychrome.Browser(url="http://127.0.0.1:9222")
        tab = browser.new_tab()
        tab.Network.requestWillBeSent = self.__request_callback
        tab.start()
        tab.Network.enable()
        tab.Page.navigate(
            url=f'https://accounts.google.com/o/saml2/initsso?idpid={aws_google_idpid}&spid={aws_google_spid}&forceauthn=false',
            _timeout=5
        )
        tab.wait(1)
        tab.stop()
        browser.close_tab(tab)
        if self.__saml is None:
            print('Error capturing SAML!')
        else:
            print(f'Captured SAML {self.__saml[0:20]}...')
        return self.__saml


class AWSConfigurer():

    def __aws_assume_role_with_saml(self, aws_account_id, aws_role, saml):
        aws_role_arn = f'arn:aws:iam::{aws_account_id}:role/{aws_role}'
        aws_principal_arn = f'arn:aws:iam::{aws_account_id}:saml-provider/g'
        print(f'Assuming role {aws_role_arn} with SAML ...')
        client = boto3.client('sts')
        response = client.assume_role_with_saml(
            RoleArn=aws_role_arn,
            PrincipalArn=aws_principal_arn,
            SAMLAssertion=saml
        )
        return response['Credentials']

    def __aws_configure(self, aws_account, aws_region, creds):
        print('Configuring profile ...')
        os.system(f'aws configure set region "{aws_region}" --profile "{aws_account}"')
        os.system(f'aws configure set aws_access_key_id "{creds["AccessKeyId"]}" --profile "{aws_account}"')
        os.system(f'aws configure set aws_secret_access_key "{creds["SecretAccessKey"]}" --profile "{aws_account}"')
        os.system(f'aws configure set aws_session_token "{creds["SessionToken"]}" --profile "{aws_account}"')
        print(f'Configured profile {aws_account} ({aws_region})')
        export_aws_profile = f'export AWS_PROFILE={aws_account}'
        copy_to_clipboard(export_aws_profile)
        print(f'To use it just execute: {export_aws_profile} (already copied to clipboard)')

    def configure(self, aws_account, aws_account_id, aws_role, aws_region, saml):
        credentials = self.__aws_assume_role_with_saml(aws_account_id, aws_role, saml)
        self.__aws_configure(aws_account, aws_region, credentials)


def copy_to_clipboard(str):
    os.system(f'echo {str} | tr -d "\n" | pbcopy')


def main(argv):
    saml_capturer = SAMLCapturer()
    saml = saml_capturer.capture_saml()
    if saml is not None:
        aws_configurer = AWSConfigurer()
        aws_configurer.configure(
            aws_account=argv[0],
            aws_account_id=argv[1],
            aws_role=argv[2],
            aws_region=argv[3],
            saml=saml
        )


if __name__ == '__main__':
    main(sys.argv[1:])
