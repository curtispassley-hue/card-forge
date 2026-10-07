"""Offline signed entitlements. Public builds remain explicitly labeled previews."""
from pathlib import Path
import base64
import hashlib
import json
import os
import platform
import sys
from copy import deepcopy
import uuid
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

PRODUCT_ID = 'cardforge-studio'
SUPPORT_EMAIL = 'curtispasley@gmail.com'


def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf-8')


def state_dir():
    root=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local'/'share')/'CardForgeStudio'
    root.mkdir(parents=True,exist_ok=True)
    return root


def device_code():
    # Only the hash is shown or used in a license. No hardware identifier is transmitted.
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Cryptography',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
            identifier=winreg.QueryValueEx(key,'MachineGuid')[0]
    except (ImportError,OSError): identifier=platform.node()+':'+str(uuid.getnode())
    return hashlib.sha256((PRODUCT_ID+':'+str(identifier)).encode()).hexdigest()[:32]


def read_config():
    if getattr(sys,'frozen',False):
        from ._build_edition import CONFIG
        config=deepcopy(CONFIG)
    else:
        path=Path(__file__).parent/'assets'/'commercial.json'
        config=json.loads(path.read_text(encoding='utf-8'))
    if config.get('edition') not in ('preview','commercial'): raise ValueError('Invalid edition configuration.')
    if config['edition']=='commercial' and not config.get('public_keys'): raise ValueError('Commercial build has no trusted license issuer.')
    return config


def verify_license(document,public_keys,device,major=1):
    try:
        if not isinstance(document,dict): raise ValueError('Invalid license file.')
        payload=document['payload'];key_id=document['key_id']
        if not isinstance(payload,dict) or not isinstance(key_id,str): raise ValueError('Invalid license claims.')
        if key_id not in public_keys: raise ValueError('License was issued by an unknown publisher key.')
        key=Ed25519PublicKey.from_public_bytes(base64.b64decode(public_keys[key_id],validate=True))
        key.verify(base64.b64decode(document['signature'],validate=True),canonical(payload))
        if payload.get('product')!=PRODUCT_ID: raise ValueError('This license is for a different product.')
        if payload.get('version')!=1 or payload.get('type')!='perpetual': raise ValueError('Unsupported license type.')
        if payload.get('device')!=device: raise ValueError('This license belongs to another computer. Request a transfer from support.')
        if not isinstance(payload.get('major_versions'),list) or major not in payload['major_versions']:
            raise ValueError('This license does not include this major version.')
        if not payload.get('license_id') or not isinstance(payload.get('customer'),str) or not payload['customer'].strip():
            raise ValueError('License customer or identifier is missing.')
        return payload
    except InvalidSignature as exc: raise ValueError('License signature is invalid. The file may have been changed.') from exc
    except (KeyError,TypeError,ValueError) as exc: raise ValueError(str(exc) or 'Invalid license file.') from exc


def license_status(config=None,directory=None,device=None):
    config=read_config() if config is None else config
    if config['edition']=='preview': return {'active':True,'edition':'preview','message':'Release candidate — commercial sales setup incomplete'}
    path=(Path(directory) if directory else state_dir())/'license.json'
    try:
        payload=verify_license(json.loads(path.read_text(encoding='utf-8')),config['public_keys'],device or device_code())
        return {'active':True,'edition':'commercial','message':'Licensed to '+payload['customer'],'payload':payload}
    except (ValueError,OSError) as exc: return {'active':False,'edition':'commercial','message':str(exc) if path.exists() else 'Activate a purchased license to export'}


def activate_license(source,config=None,directory=None,device=None):
    config=read_config() if config is None else config
    if config['edition']!='commercial': raise ValueError('This preview does not use paid activation. Install the publisher’s commercial edition to activate.')
    raw=Path(source).read_bytes()
    if len(raw)>16384: raise ValueError('License file is too large.')
    document=json.loads(raw.decode('utf-8'))
    payload=verify_license(document,config['public_keys'],device or device_code())
    folder=Path(directory) if directory else state_dir();folder.mkdir(parents=True,exist_ok=True)
    dest=folder/'license.json';temporary=folder/('license_'+uuid.uuid4().hex+'.tmp')
    try: temporary.write_text(json.dumps(document),encoding='utf-8');temporary.replace(dest)
    finally: temporary.unlink(missing_ok=True)
    return payload


def deactivate_license(directory=None):
    (Path(directory) if directory else state_dir()).joinpath('license.json').unlink(missing_ok=True)
