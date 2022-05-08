# AWS Google Give Me Credentials

## Use

* Configure SAML IDPID and SPID as environment variables (used to generate the SAML endpoint URL):
    ```shell
    export AWS_GOOGLE_IDPID=xxx
    export AWS_GOOGLE_SPID=xxx
    ```

* Start Google Chrome with remote debugging:
    ```shell
    # On Mac:
    killall 'Google Chrome'
    /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 &
    ```

* Execute **aws-google-gimme-creds** script:
    ```shell
    python3 aws-google-gimme-creds.py {aws-account} {aws-account-id} {aws-role} {aws-region}
    ```

## References
* [pychrome](https://github.com/fate0/pychrome)
* [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/tot/)