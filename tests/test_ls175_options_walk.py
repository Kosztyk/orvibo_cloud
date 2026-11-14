"""Actually execute the restored options-flow methods in a pure-Python HA stub.

Catches accidental short-circuits that drop the pre-existing multi-page wizard.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

FLOW = Path(__file__).resolve().parents[1] / 'custom_components/orvibo_cloud/config_flow.py'

class RfOptions:
    def __init__(self, remember=False, restore=False, expiry_minutes=0):
        self.remember = remember
        self.restore = restore
        self.expiry_minutes = expiry_minutes
    def as_dict(self):
        return {'remember_assumed_state': self.remember,
                'restore_assumed_state': self.restore,
                'assumed_state_expiry_minutes': self.expiry_minutes}

class FakeVol:
    class Invalid(Exception): pass
    @staticmethod
    def Required(name, default=None): return name
    @staticmethod
    def Optional(name, default=None): return name
    @staticmethod
    def Schema(obj): return obj

class FakeSelector:
    class SelectSelectorMode: DROPDOWN='dropdown'
    @staticmethod
    def SelectOptionDict(**kwargs): return kwargs
    @staticmethod
    def SelectSelectorConfig(**kwargs): return kwargs
    @staticmethod
    def SelectSelector(cfg): return cfg


def load_flow():
    tree = ast.parse(FLOW.read_text())
    cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OrviboCloudOptionsFlow')
    cls.bases = []
    cls.keywords = []
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    registry = SimpleNamespace(async_get_device_by_identifier=lambda *args: None,
                               async_update_device=lambda *args,**kw:None)
    ns = {
        'Any': object, 'FlowResult':dict, 'OrviboDevice':object,
        'vol':FakeVol, 'selector':FakeSelector,
        'DOMAIN':'orvibo_cloud', 'CONF_HOST':'host', 'CONF_EMAIL':'email',
        'CONF_PASSWORD_HASH':'password_hash', 'CONF_FAMILY_ID':'family_id',
        'CONF_USER_ID':'user_id', 'CONF_SELECTED_DEVICE_IDS':'selected_device_ids',
        'CONF_RAW_EVENT_CAPTURE':'raw_event_capture',
        'CONF_DEVICE_AREAS':'device_areas', 'CONF_RF_BLIND_OPTIONS':'rf_blind_options',
        'CONF_SPEAKER_IR_MODELS':'speaker_ir_models', 'CONF_STATE_EXPIRY':'assumed_state_expiry_minutes',
        'ATTR_AREA_ID':'area_id', 'ORVIBO_HOSTS':{'homemate.orvibo.com'},
        'SPEAKER_MODEL_NONE':'none', 'SUPPORTED_SPEAKER_IR_MODELS':{'blaupunkt_ls175'},
        'RFBlindOptions':RfOptions, '_host_selector':lambda:{'host-selector':True},
        '_device_schema':lambda devices,default:{'choices':[d.uid for d in devices], 'default':default},
        'selected_device_ids':lambda options,uids:set(options.get('selected_device_ids',uids)),
        'configured_device_areas':lambda options:dict(options.get('device_areas',{})),
        'configured_rf_blind_options':lambda options: {
            uid:RfOptions(o['remember_assumed_state'],o['restore_assumed_state'],o['assumed_state_expiry_minutes'])
            for uid,o in options.get('rf_blind_options',{}).items()
        },
        'configured_speaker_ir_models':lambda opts:dict(opts.get('speaker_ir_models',{})),
        '_rf_options_from_input':lambda u:RfOptions(u.get('remember_assumed_state') is True,
                                                    u.get('restore_assumed_state') is True,
                                                    u.get('assumed_state_expiry_minutes',0)),
        'is_rf_curtain':lambda d,ds:d.device_type=='34',
        'is_ls175_test_target':lambda d,ds:d.device_type=='7',
        '_default_area_id':lambda hass,d,areas:areas.get(d.uid),
        '_area_schema':lambda area,rf=None,speaker=None:{'area_id':area, 'rf_control':rf is not None, 'speaker_ir_model':speaker},
        '_device_categories':lambda ds:{d.uid:'Other' for d in ds},
        '_device_label':lambda d,c:d.name,
        '_rf_settings_note':lambda *args:'',
        'dr':SimpleNamespace(async_get=lambda hass:registry),
    }
    exec(compile(module,str(FLOW),'exec'),ns)
    return ns['OrviboCloudOptionsFlow']

class WalkEntireWizard(unittest.IsolatedAsyncioTestCase):
    async def test_full_original_steps_and_options_survive(self):
        Flow = load_flow()
        f = Flow()
        devices=(SimpleNamespace(uid='blind-uid',name='Blind',device_type='34',room='Bedroom'),
                 SimpleNamespace(uid='speaker-uid',name='Bedroom soundbar',device_type='7',room='Bedroom'),
                 SimpleNamespace(uid='tv-uid',name='Luigi',device_type='6',room='Bedroom'))
        existing={'selected_device_ids':[d.uid for d in devices],
                  'device_areas':{d.uid:'bedroom' for d in devices},
                  'rf_blind_options':{'blind-uid':RfOptions(True,True,60).as_dict()},
                  'tv_profile':'stored', 'raw_event_capture':True,
                  'custom_untouched_setting':'preserve-me'}
        f.config_entry=SimpleNamespace(entry_id='entry-1',
                        data={'host':'homemate.orvibo.com'},options=existing)
        f.hass=SimpleNamespace(data={'orvibo_cloud':{'entry-1':SimpleNamespace(data=SimpleNamespace(devices=devices))}})
        f.async_show_form=lambda **kw:{'type':'form',**kw}
        f.async_create_entry=lambda **kw:{'type':'create_entry',**kw}
        first=await f.async_step_init()
        self.assertEqual(first['step_id'],'init')
        self.assertEqual(set(first['data_schema']),{'host','tv_profile','raw_event_capture'})
        second=await f.async_step_init({'host':'homemate.orvibo.com',
                                         'tv_profile':'stored','raw_event_capture':True})
        self.assertEqual(second['step_id'],'devices')
        self.assertEqual(second['data_schema']['default'],existing['selected_device_ids'])
        blind=await f.async_step_devices({'selected_device_ids':existing['selected_device_ids']})
        self.assertEqual(blind['step_id'],'area')
        self.assertEqual(blind['data_schema']['rf_control'],True)
        self.assertIsNone(blind['data_schema']['speaker_ir_model'])
        speaker=await f.async_step_area({'area_id':'bedroom','remember_assumed_state':True,
                                         'restore_assumed_state':True,
                                         'assumed_state_expiry_minutes':60})
        self.assertEqual(speaker['step_id'],'area')
        self.assertEqual(speaker['data_schema']['speaker_ir_model'],'none')
        tv=await f.async_step_area({'area_id':'bedroom','speaker_ir_model':'blaupunkt_ls175'})
        self.assertEqual(tv['step_id'],'area')
        self.assertFalse(tv['data_schema']['rf_control'])
        done=await f.async_step_area({'area_id':'bedroom'})
        self.assertEqual(done['type'],'create_entry')
        opts=done['data']
        self.assertEqual(opts['speaker_ir_models'],{'speaker-uid':'blaupunkt_ls175'})
        self.assertEqual(opts['rf_blind_options'],existing['rf_blind_options'])
        self.assertEqual(opts['selected_device_ids'],existing['selected_device_ids'])
        self.assertEqual(opts['device_areas'],existing['device_areas'])
        for k in ('tv_profile','raw_event_capture','custom_untouched_setting'):
            self.assertEqual(opts[k],existing[k])
        self.assertNotIn('speaker_ir_models',existing) # Nothing persisted prematurely

if __name__=='__main__':unittest.main()
