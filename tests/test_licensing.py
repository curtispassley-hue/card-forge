import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cardforge.licensing import canonical,PRODUCT_ID,verify_license,license_status,activate_license,deactivate_license


class LicenseTests(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.config={'edition':'commercial','public_keys':{'test':base64.b64encode(public).decode()}}
        self.device='1'*32
        self.payload={'version':1,'product':PRODUCT_ID,'type':'perpetual','license_id':'test-license','customer':'Example Customer','device':self.device,'major_versions':[1]}

    def signed(self,payload=None):
        payload=payload or self.payload
        return {'key_id':'test','payload':payload,'signature':base64.b64encode(self.key.sign(canonical(payload))).decode()}

    def test_valid_offline_activation_status_and_deactivation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'purchased.json';source.write_text(json.dumps(self.signed()))
            self.assertFalse(license_status(self.config,root,self.device)['active'])
            activate_license(source,self.config,root,self.device)
            source.unlink()
            status=license_status(self.config,root,self.device)
            self.assertTrue(status['active']);self.assertEqual(status['payload']['customer'],'Example Customer')
            deactivate_license(root)
            self.assertFalse(license_status(self.config,root,self.device)['active'])

    def test_tamper_other_device_and_wrong_entitlement_are_rejected(self):
        altered=copy.deepcopy(self.signed());altered['payload']['device']='2'*32
        with self.assertRaisesRegex(ValueError,'signature'): verify_license(altered,self.config['public_keys'],'2'*32)
        with self.assertRaisesRegex(ValueError,'another computer'): verify_license(self.signed(),self.config['public_keys'],'2'*32)
        for key,value in [('product','other'),('major_versions',[2]),('customer','')]:
            payload=copy.deepcopy(self.payload);payload[key]=value
            with self.assertRaises(ValueError): verify_license(self.signed(payload),self.config['public_keys'],self.device)
        foreign=copy.deepcopy(self.signed());foreign['key_id']='unknown'
        with self.assertRaisesRegex(ValueError,'unknown publisher'): verify_license(foreign,self.config['public_keys'],self.device)

    def test_failed_activation_preserves_existing_license(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'purchase.json';source.write_text(json.dumps(self.signed()))
            activate_license(source,self.config,root,self.device)
            previous=(root/'license.json').read_bytes()
            altered=copy.deepcopy(self.signed());altered['payload']['customer']='Changed'
            source.write_text(json.dumps(altered))
            with self.assertRaises(ValueError): activate_license(source,self.config,root,self.device)
            self.assertEqual((root/'license.json').read_bytes(),previous)


if __name__=='__main__': unittest.main()
