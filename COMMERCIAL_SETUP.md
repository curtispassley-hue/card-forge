# CardForge Studio publisher setup

Support email configured in the app: curtispasley@gmail.com. The brand is CardForge Studio; a legal publisher name has not been provided. This public build is a release candidate and intentionally uses `edition: preview`, with unrestricted testing exports. It must not be sold as a completed, signed production release.

## Licensing model implemented

A commercial build verifies Ed25519-signed perpetual license files offline. Entitlements are limited to a major version and a device code. Customers can edit and save projects before activation; geometry exports require activation. No customer data or hardware ID is automatically sent to a server. Only a hash of the Windows machine identifier is displayed as the device code. Hardware/Windows reinstall can change that code; support must reissue a license when appropriate. Deactivation removes the local file, not the customer's saved license copy. Offline licenses cannot be remotely revoked; a transfer policy must acknowledge this limitation. This is not tamper-proof DRM.

`cardforge/assets/commercial.json` ships only public issuer keys. `scripts/license_admin.py` is an owner-only tool, excluded from the packaged executable. NEVER commit or distribute private issuer keys, passwords, payment credentials, customer license records, or signing certificates. Back up the encrypted issuer key separately and securely.

Create an issuer using the source environment (replace example paths and publisher with real values):

```
python scripts/license_admin.py create-issuer --private-key C:/CardForgeSecrets/issuer.pem --public-config C:/CardForgeSecrets/commercial-public.json --publisher "YOUR LEGAL PUBLISHER" --support-email curtispasley@gmail.com
```

The tool prompts for a private-key password of at least 12 characters. Copy only `commercial-public.json` over `cardforge/assets/commercial.json` in the intended commercial build. Retain trusted older public keys if rotating issuers. Build and test that configuration before distributing it. The packaging step embeds these public settings into the executable; editing a JSON file beside an installed app does not change its edition or trusted issuer keys.

After verifying an actual purchase, ask the customer for the device code from **License > Copy device code**, then issue a license:

```
python scripts/license_admin.py issue --private-key C:/CardForgeSecrets/issuer.pem --customer "CUSTOMER NAME OR EMAIL" --device CUSTOMER_32_HEX_DEVICE_CODE --major 1 --output C:/CardForgeOrders/customer-license.json
```

Record the purchase, customer, license ID, device hash, major version and transfer history in a private order system. Deliver the signed JSON with instructions to use **Activate license file**. Activation validates the signature before replacing an installed license. The script never accepts a private key stored inside the source repository. Example secret paths are suggestions; they are not created by this release.

## Before taking payments

1. Choose the legal publisher, price, refund policy, support scope, transfer policy and customer-facing terms. Configure a real purchase/support delivery route. No payment processor or checkout was created, and no money is collected by the app.
2. Audit ownership of application code, icons, fonts, OCR models and every bundled dependency. Builds collect available notices and pin 30 OFL font files. This inventory is evidence for review, not a legal clearance certificate.
3. Preserve `LICENSE.txt` and third-party notices. The existing public source license allows commercial redistribution with its conditions; an activation feature cannot cancel those source rights. Do not claim exclusive licensing of already published MIT-style code. Proprietary rights changes require ownership/legal review and cannot erase public history.
4. Obtain a Windows code-signing certificate through the owner and sign the app and installer with timestamping. Signing credentials must stay outside the repository and public artifacts. This workflow publishes unsigned RCs; a commercial signing pipeline still needs owner credentials and verification. A clean Defender scan is not code signing and cannot guarantee all antivirus products.
5. Physically validate A1 first layers, lettering/logo details, NFC fit, panel fit, shell/back retention, LED clearance/cable routing, temperature, light uniformity and stand/wall mounting with the chosen lighting kit. The default strip profile has unverified cut spacing/thickness. Validate customer instructions and retention hardware; the current friction back is not a secured enclosure.
6. Test commercial activation on a fresh Windows computer, wrong-device and damaged licenses, version entitlement, reinstall/transfer, installed and portable app updates, backup/recovery and uninstall. Current automated tests cover cryptographic validation and export gating logic; a real customer purchase-to-delivery test remains.
7. Publish a production release only after these gates pass, with hashes, signed binaries, license/notice files, installation instructions and support documents. Never label an RC as production because its automated tests pass.

## Building and installation

Install Python 3.12 requirements, run `python scripts/fetch_fonts.py`, `python -m unittest discover -v`, and `python main.py --self-test source-test.json`. Build with `pyinstaller --noconfirm --clean CardForge4D.spec`, then compile `installer/CardForgeStudio.iss` with Inno Setup 6. The workflow repeats tests on portable and installed executables and verifies uninstall. It does not remove customer projects or `%LOCALAPPDATA%/CardForgeStudio` during uninstall.

Windows 10/11 x64 is the target. Keep the whole portable directory intact. Imported artwork may carry its own trademark/copyright restrictions; customers should have rights to images they distribute. Nothing in this app grants artwork rights.
