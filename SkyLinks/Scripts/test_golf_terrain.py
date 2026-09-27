"""Offline acceptance checks for generated terrain; no Unreal dependency."""
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
from PIL import Image

TERRAIN=Path(__file__).resolve().parents[1]/'Art/Terrain'
BATCHES={'Holes01-06':range(1,7),'Holes07-18':range(7,19)}

class TerrainAcceptance(unittest.TestCase):
    def test_files_encoding_and_surface_coverage(self):
        for name,holes in BATCHES.items():
            folder=TERRAIN/name
            m=json.loads((folder/'manifest.json').read_text())
            self.assertEqual([int(h['label'][-2:]) for h in m['holes']],list(holes))
            for h in m['holes']:
                with self.subTest(hole=h['label']):
                    g=h['grid']; layers=[]
                    for kind,entry in h['files'].items():
                        p=folder/entry['file']
                        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),entry['sha256'])
                        im=Image.open(p)
                        self.assertEqual(im.size,(g['W'],g['H']))
                        if kind=='height':
                            self.assertEqual(p.read_bytes()[24],16,'PNG IHDR must specify 16-bit depth')
                            a=np.array(im,dtype=float)
                            self.assertGreater(len(np.unique(a)),1000,'Reject accidental 8-bit height quantization')
                            z=(a-32768)/128*m['scale_z']+m['actor_z_cm']
                            self.assertTrue(np.isfinite(z).all())
                            self.assertGreaterEqual(z.min(),-61)
                            self.assertLess(z.max(),100)
                        else:
                            layers.append(np.array(im,dtype=np.int32))
                    np.testing.assert_array_equal(sum(layers),np.full((g['H'],g['W']),255))
                    if 'create' in h:
                        # New landscapes: valid Unreal sizes (63-quad sections) and at most 40 cm spacing.
                        for count in h['create']['resolution']:
                            self.assertEqual((count-1)%63,0)
                        self.assertLessEqual(max(h['create']['scale'][:2]),40.0001)

    def test_world_space_gameplay_points(self):
        for name,holes in BATCHES.items():
            samples=json.loads((TERRAIN/name/'validation_samples.json').read_text())
            for p in samples:
                with self.subTest(hole=p['hole'],kind=p['kind'],x=p['x'],y=p['y']):
                    if p['kind']=='tee':self.assertAlmostEqual(p['expected_z'],0,delta=.002)
                    if p['kind']=='water':self.assertLess(p['landscape_z'],-50)
            for hole in holes:
                g=[p for p in samples if p['hole']==hole and p['kind']=='green']
                self.assertEqual(len(g),5)
                self.assertAlmostEqual(g[0]['expected_z'],30,delta=.002)
                sx=(g[1]['expected_z']-g[2]['expected_z'])/1000
                sy=(g[3]['expected_z']-g[4]['expected_z'])/1000
                self.assertGreater(np.hypot(sx,sy),.01)
                self.assertLess(np.hypot(sx,sy),.02)

if __name__=='__main__':unittest.main()
