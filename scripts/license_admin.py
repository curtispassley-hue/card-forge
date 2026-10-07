"""Owner-only issuer. This tool and private keys are not bundled in the app."""
import argparse
import base64
import getpass
import json
import sys
import uuid
from datetime import datetime,timezone
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cardforge.licensing import canonical,PRODUCT_ID,verify_license


def main():
    parser=argparse.ArgumentParser(description='CardForge offline license issuer — keep private keys outside source and releases')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('create-issuer');init.add_argument('--private-key',required=True);init.add_argument('--public-config',required=True);init.add_argument('--publisher',required=True);init.add_argument('--support-email',required=True)
    issue=sub.add_parser('issue');issue.add_argument('--private-key',required=True);issue.add_argument('--customer',required=True);issue.add_argument('--device',required=True);issue.add_argument('--output',required=True);issue.add_argument('--major',type=int,default=1)
    args=parser.parse_args()
    key_path=Path(args.private_key).resolve()
    repo=Path(__file__).resolve().parents[1]
    if key_path.is_relative_to(repo): parser.error('Private keys must be stored outside the source repository.')
    password=getpass.getpass('Private-key password: ').encode()
    if len(password)<12: parser.error('Use a password of at least 12 characters.')
    if args.command=='create-issuer':
        if key_path.exists(): parser.error('A key already exists at this path; refusing to replace it.')
        if password!=getpass.getpass('Repeat password: ').encode(): parser.error('Passwords do not match.')
        public_path=Path(args.public_config)
        if public_path.exists(): parser.error('Public configuration already exists; use a new output path.')
        key=Ed25519PrivateKey.generate()
        public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        import hashlib
        kid=hashlib.sha256(public).hexdigest()[:16]
        key_path.parent.mkdir(parents=True,exist_ok=True)
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(password)))
        config={'edition':'commercial','publisher':args.publisher,'support_email':args.support_email,'purchase_url':'','public_keys':{kid:base64.b64encode(public).decode()}}
        public_path.parent.mkdir(parents=True,exist_ok=True);public_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
        print('Encrypted private issuer key created. Back it up securely; ship only the public configuration.')
    else:
        if len(args.device)!=32 or any(c not in '0123456789abcdef' for c in args.device): parser.error('Paste the 32-character device code shown in the customer app.')
        if args.major<1: parser.error('Major version must be a positive integer.')
        output=Path(args.output)
        if output.exists(): parser.error('License output already exists; refusing to overwrite it.')
        key=serialization.load_pem_private_key(key_path.read_bytes(),password=password)
        if not isinstance(key,Ed25519PrivateKey): parser.error('This is not an Ed25519 issuer key.')
        public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        import hashlib
        kid=hashlib.sha256(public).hexdigest()[:16]
        payload={'version':1,'product':PRODUCT_ID,'type':'perpetual','license_id':str(uuid.uuid4()),'customer':args.customer.strip(),'device':args.device,'major_versions':[args.major],'issued_at':datetime.now(timezone.utc).isoformat()}
        document={'key_id':kid,'payload':payload,'signature':base64.b64encode(key.sign(canonical(payload))).decode()}
        verify_license(document,{kid:base64.b64encode(public).decode()},args.device,args.major)
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(document,indent=2),encoding='utf-8')
        print('Signed perpetual license written. Record the license ID and purchase/device history before delivery.')


if __name__=='__main__': main()
