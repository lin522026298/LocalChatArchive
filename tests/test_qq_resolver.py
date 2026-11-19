"""QQ verification boundaries, without a real archive or QQ executable."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'local-chat-archive/scripts'))
from chat_archive import Refusal, copy_qq, qq_items


class QqResolverTests(unittest.TestCase):
    def setUp(self):
        work=tempfile.TemporaryDirectory();self.addCleanup(work.cleanup)
        self.root=Path(work.name).resolve()
        self.state=self.root/'archive';self.state.mkdir()
        self.payload=b'fixture for QQ original checks'
        self.sha=hashlib.sha256(self.payload).hexdigest()
        self.src=self.state/self.sha;self.src.write_bytes(self.payload)
        self.link=dict(role='primary',verification='verified_content',segment_index=0,
                       filename='fixture.bin',primary={'path':str(self.src)})

    def test_candidate_cannot_be_promoted_by_matching_filename_or_hash(self):
        value,path=next(qq_items([dict(self.link,verification='filename_only')],self.state))
        self.assertEqual(value['status'],'candidate_or_unavailable')
        self.assertIsNone(path)

    def test_outside_archive_original_is_not_delivered(self):
        outside=self.root/self.sha;outside.write_bytes(self.payload)
        value,path=next(qq_items([dict(self.link,primary={'path':str(outside)})],self.state))
        self.assertEqual(value['status'],'original_missing_or_outside_selected_archive')
        self.assertIsNone(path)

    def test_corruption_is_detected_and_existing_target_is_never_overwritten(self):
        name=self.root/'fixture.bin'
        self.src.write_bytes(b'corrupted fixture')
        with self.assertRaisesRegex(Refusal,'attachment_hash_mismatch'):copy_qq(self.src,name,self.sha)
        self.assertFalse(name.exists())
        self.src.write_bytes(self.payload)
        self.assertTrue(copy_qq(self.src,name,self.sha)['verified'])
        with self.assertRaises(FileExistsError):copy_qq(self.src,name,self.sha)
        self.assertEqual(name.read_bytes(),self.payload)
