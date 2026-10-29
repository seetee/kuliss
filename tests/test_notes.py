import io
import unittest
import tempfile
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock
from xml.sax.saxutils import escape

from kuliss import notes as kc


def kdenlive_xml(notes_html=None, version='24.12.3'):
    props = []
    if version:
        props.append(
            f'<property name="kdenlive:docproperties.kdenliveversion">{version}</property>'
        )
    if notes_html is not None:
        props.append(
            f'<property name="kdenlive:documentnotes">{escape(notes_html)}</property>'
        )
    return f'<mlt><playlist id="main_bin">{"".join(props)}</playlist></mlt>'


def note(ts, text):
    return f'<p><a href="{ts}">{ts}</a> {text}</p>'


def heading(name):
    return f'<p>## {name}</p>'


NOTEWORTHY = (
    heading('Noteworthy')
    + note('00:06:29:32', 'A memorable quote -h')
    + note('00:03:12:01', 'Earlier moment -j')
)


class SessionTree:
    """Builds a session directory tree inside a temp dir."""

    def __init__(self, tmp, name='session_26_2025-06-30'):
        self.dir = Path(tmp) / name
        self.dir.mkdir(parents=True)

    def episode(self, name, notes_html=None, version='24.12.3', raw=None):
        ep = self.dir / name
        ep.mkdir()
        content = raw if raw is not None else kdenlive_xml(notes_html, version)
        (ep / f'{name}.kdenlive').write_text(content, encoding='utf-8')
        return ep

    @property
    def md(self):
        return self.dir / f'{self.dir.name}.md'

    def run(self, dry_run=False):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.warnings = kc.process_session(self.dir, dry_run=dry_run)
        self.stdout = buf.getvalue()
        return self.md.read_text(encoding='utf-8') if self.md.exists() else ''


class BootstrapTests(unittest.TestCase):

    def test_full_skeleton_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            out = t.run()
            expected_order = [
                '# Session 26 - 2025-06-30',
                '## Mjukvaruversioner',
                '* Prism Launcher 9.2',
                '* OBS 23.0.3',
                '* Kdenlive 24.12.3',
                '## Avsnittsinfo',
                '### avsnitt207',
                '**Titel:**',
                '**Blurb (large):**',
                '**Blurb (short):**',
                '**Trailer:**',
                '#### Noteworthy',
                '* 03:12 Earlier moment -j',
                '* 06:29 A memorable quote -h',
            ]
            positions = [out.index(s) for s in expected_order]
            self.assertEqual(positions, sorted(positions))
            self.assertNotIn('#### Bryggpromenader', out)
            self.assertNotIn('#### Other comments without a home', out)

    def test_hour_timestamps_keep_hours(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', heading('Noteworthy') + note('01:02:03:10', 'Long -k'))
            out = t.run()
            self.assertIn('* 01:02:03 Long -k', out)

    def test_natural_episode_sort(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt10', NOTEWORTHY)
            t.episode('avsnitt9', NOTEWORTHY)
            out = t.run()
            self.assertLess(out.index('### avsnitt9'), out.index('### avsnitt10'))


class PlacementTests(unittest.TestCase):

    def test_sections_stay_inside_episode_despite_trailing_h2(self):
        """Regression: '## Övrigt' after the last episode must not swallow notes."""
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                '**Titel:** Ett avsnitt\n'
                '**Blurb (large):** Lång\n'
                '**Blurb (short):** Kort\n'
                '**Trailer:** Trailerinfo\n\n'
                '## Övrigt\n\n'
                '* keep me\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertIn('* keep me', out)
            self.assertLess(out.index('#### Noteworthy'), out.index('## Övrigt'))
            self.assertLess(out.index('* 06:29 A memorable quote -h'), out.index('## Övrigt'))

    def test_missing_episode_heading_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n## Avsnittsinfo\n', encoding='utf-8'
            )
            out = t.run()
            self.assertIn('### avsnitt207', out)
            self.assertIn('**Titel:**', out)
            self.assertIn('* 06:29 A memorable quote -h', out)


class RepairTests(unittest.TestCase):

    def test_missing_metadata_fields_added_values_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                '**Titel:** Behåll mig\n\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertIn('**Titel:** Behåll mig', out)
            for field in ('Blurb (large)', 'Blurb (short)', 'Trailer'):
                self.assertIn(f'**{field}:**', out)

    def test_unbolded_metadata_gets_stars_without_duplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                'Titel: Min titel\n'
                'Blurb (large): Lång text\n'
                'Trailer:\n\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertIn('**Titel:** Min titel', out)
            self.assertIn('**Blurb (large):** Lång text', out)
            self.assertIn('**Trailer:**', out)
            self.assertEqual(out.count('Titel:'), 1)
            self.assertEqual(out.count('Blurb (large):'), 1)
            self.assertEqual(out.count('Trailer:'), 1)

    def test_empty_orphan_section_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                '**Titel:** X\n\n'
                '#### Noteworthy\n\n'
                '#### Other comments without a home\n\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertNotIn('#### Other comments without a home', out)

    def test_stale_orphan_bullets_migrated_without_duplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', '<p>stray comment</p>' + NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                '**Titel:** X\n\n'
                '#### Other comments without a home\n'
                '* stray comment\n\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertNotIn('#### Other comments without a home', out)
            self.assertEqual(out.count('* stray comment'), 1)

    def test_missing_top_sections_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text('# Session 26 - 2025-06-30\n', encoding='utf-8')
            out = t.run()
            self.assertLess(out.index('## Mjukvaruversioner'), out.index('## Avsnittsinfo'))
            self.assertIn('* Prism Launcher 9.2', out)

    def test_software_version_line_updated_hand_lines_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY, version='25.04.0')
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Mjukvaruversioner\n\n'
                '* OBS 23.0.3 (my hand-tuned line)\n'
                '* Kdenlive 23.08.0\n\n'
                '## Avsnittsinfo\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertIn('* OBS 23.0.3 (my hand-tuned line)', out)
            self.assertIn('* Kdenlive 25.04.0', out)
            self.assertNotIn('* Kdenlive 23.08.0', out)


class ContentPreservationTests(unittest.TestCase):

    def test_hand_bullets_survive_when_no_incoming_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                '**Titel:** X\n\n'
                '#### Other comments without a home\n'
                '* my own hand-written note\n\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertIn('* my own hand-written note', out)
            self.assertIn('#### Other comments without a home', out)

    def test_old_bullets_replaced_when_notes_arrive(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                '#### Noteworthy\n'
                '* 01:00 stale old bullet\n\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertNotIn('stale old bullet', out)
            self.assertIn('* 06:29 A memorable quote -h', out)

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            brygg = (
                heading('Bryggpromenader')
                + note('00:05:28:00', 'H+1')
                + note('00:12:03:00', 'J+1')
            )
            starred = note('00:07:00:00', '* Kapitelgräns -j')
            t.episode('avsnitt207', '<p>stray orphan</p>' + NOTEWORTHY + starred + brygg)
            first = t.run()
            second = t.run()
            self.assertEqual(first, second)


class BryggpromenadTests(unittest.TestCase):

    def test_tally_auto_counted_one_name_per_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            brygg = (
                heading('Bryggpromenader')
                + note('00:05:28:00', 'H+1')
                + note('00:12:03:00', 'J+1')
                + note('00:31:44:00', 'H+1')
            )
            t.episode('avsnitt207', NOTEWORTHY + brygg)
            out = t.run()
            self.assertIn('#### Bryggpromenader', out)
            self.assertIn('Joel: 1\nRobin: 0\nHenrik: 2\nKenneth: 0\n', out)

    def test_section_omitted_without_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            out = t.run()
            self.assertNotIn('#### Bryggpromenader', out)


BRYGG = (
    heading('Bryggpromenader')
    + note('00:05:28:00', 'H+1')
    + note('00:12:03:00', 'J+1 and K+1')
)


class ChapterTests(unittest.TestCase):

    def test_starred_note_becomes_chapter_star_stripped_from_bullet(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            html = heading('Noteworthy') + note('00:06:29:32', '* Grottan öppnas -h')
            t.episode('avsnitt207', html)
            out = t.run()
            self.assertIn('* 06:29 Grottan öppnas -h', out)
            self.assertNotIn('* 06:29 * Grottan', out)
            self.assertIn(
                '#### Kapitel\n'
                '00:00 Äventyret börjar!\n'
                '06:29 Grottan öppnas\n',
                out,
            )

    def test_brygg_entries_become_named_chapters_in_time_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            starred = note('00:06:29:32', '* Grottan öppnas -h')
            t.episode('avsnitt207', NOTEWORTHY + starred + BRYGG)
            out = t.run()
            self.assertIn(
                '#### Kapitel\n'
                '00:00 Äventyret börjar!\n'
                '05:28 Henrik tar en lång promenad på en kort brygga\n'
                '06:29 Grottan öppnas\n'
                '12:03 Joel och Kenneth tar en lång promenad på en kort brygga\n',
                out,
            )

    def test_no_chapters_no_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            out = t.run()
            self.assertNotIn('#### Kapitel', out)

    def test_stale_managed_only_kapitel_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                '**Titel:** X\n\n'
                '#### Kapitel\n'
                '00:00 Äventyret börjar!\n'
                '03:00 Gammalt kapitel\n\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertNotIn('#### Kapitel', out)

    def test_hand_written_line_in_kapitel_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY + BRYGG)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                '**Titel:** X\n\n'
                '#### Kapitel\n'
                'OBS: dubbelkolla kapitlen\n\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertIn('00:00 Äventyret börjar!', out)
            self.assertIn('OBS: dubbelkolla kapitlen', out)


class ExtractionTests(unittest.TestCase):

    def test_orphan_notes_appended_to_noteworthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            html = (
                note('00:02:00:00', 'orphan with timestamp')
                + '<p>plain stray comment</p>'
                + NOTEWORTHY
            )
            t.episode('avsnitt207', html)
            out = t.run()
            self.assertNotIn('#### Other comments without a home', out)
            self.assertIn(
                '#### Noteworthy\n'
                '* 03:12 Earlier moment -j\n'
                '* 06:29 A memorable quote -h\n'
                '\n'
                '* 02:00 orphan with timestamp\n'
                '* plain stray comment\n',
                out,
            )

    def test_orphans_alone_become_noteworthy_bullets(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', '<p>only a stray comment</p>')
            out = t.run()
            self.assertNotIn('#### Other comments without a home', out)
            self.assertIn('#### Noteworthy\n* only a stray comment\n', out)

    def test_malformed_kdenlive_does_not_abort_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', raw='<mlt><broken')
            t.episode('avsnitt208', NOTEWORTHY)
            out = t.run()
            self.assertIn('### avsnitt208', out)
            self.assertIn('* 06:29 A memorable quote -h', out)


PARTIAL_MD = (
    '# Session 26 - 2025-06-30\n\n'
    '## Avsnittsinfo\n\n'
    '### avsnitt207\n\n'
    '**Titel:** X\n'
)


class SafetyTests(unittest.TestCase):

    def test_backup_contains_previous_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(PARTIAL_MD, encoding='utf-8')
            t.run()
            bak = t.dir / (t.md.name + '.bak')
            self.assertEqual(bak.read_text(encoding='utf-8'), PARTIAL_MD)
            t.run()  # no-op run must not touch the backup
            self.assertEqual(bak.read_text(encoding='utf-8'), PARTIAL_MD)

    def test_no_backup_on_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.run()
            self.assertFalse((t.dir / (t.md.name + '.bak')).exists())

    def test_dry_run_prints_diff_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(PARTIAL_MD, encoding='utf-8')
            out = t.run(dry_run=True)
            self.assertEqual(out, PARTIAL_MD)
            self.assertIn('dry run', t.stdout)
            self.assertIn('+#### Noteworthy', t.stdout)
            self.assertFalse((t.dir / (t.md.name + '.bak')).exists())

    def test_note_whitespace_collapsed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            html = heading('Noteworthy') + note('00:06:29:32', 'first line\nsecond\tline')
            t.episode('avsnitt207', html)
            first = t.run()
            self.assertIn('* 06:29 first line second line', first)
            self.assertEqual(first, t.run())

    def test_stale_section_warns_and_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt999\n\n'
                '**Titel:** Gammal\n',
                encoding='utf-8',
            )
            out = t.run()
            self.assertIn('### avsnitt999', out)
            self.assertIn('**Titel:** Gammal', out)
            self.assertGreaterEqual(t.warnings, 1)
            self.assertIn('no matching episode directory', t.stdout)

    def test_parse_failure_counts_as_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', raw='<mlt><broken')
            t.run()
            self.assertEqual(t.warnings, 1)


class ShowTests(unittest.TestCase):

    def test_show_episode_prints_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.run()
            buf = io.StringIO()
            with redirect_stdout(buf):
                found = kc._show_episode(t.dir, 'avsnitt207')
            self.assertTrue(found)
            shown = buf.getvalue()
            self.assertIn('### avsnitt207', shown)
            self.assertIn('**Titel:**', shown)
            self.assertIn('* 06:29 A memorable quote -h', shown)

    def test_show_missing_episode_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.run()
            self.assertFalse(kc._show_episode(t.dir, 'avsnitt999'))


class LimitCheckTests(unittest.TestCase):

    def test_long_titel_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            long_title = 'x' * 120
            t.md.write_text(
                '# Session 26 - 2025-06-30\n\n'
                '## Avsnittsinfo\n\n'
                '### avsnitt207\n\n'
                f'**Titel:** {long_title}\n\n',
                encoding='utf-8',
            )
            t.run()
            self.assertIn('Titel too long (120/100 chars)', t.stdout)

    def test_too_few_chapters_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            starred = note('00:06:29:32', '* Grottan öppnas -h')
            t.episode('avsnitt207', heading('Noteworthy') + starred)
            t.run()  # 00:00 opener + 1 starred = 2 chapters
            self.assertIn('only 2 chapters (YouTube needs 3+)', t.stdout)

    def test_three_chapters_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            starred = note('00:06:29:32', '* Grottan öppnas -h')
            t.episode('avsnitt207', heading('Noteworthy') + starred + BRYGG)
            t.run()  # opener + starred + 2 brygg = 4 chapters
            self.assertNotIn('YouTube needs 3+', t.stdout)


class ScaffoldTests(unittest.TestCase):

    def _scaffold(self, start, answers=None):
        buf = io.StringIO()
        side_effect = answers if answers is not None else EOFError
        with redirect_stdout(buf), mock.patch('builtins.input', side_effect=side_effect):
            kc.scaffold_session(start)
        return buf.getvalue()

    def test_creates_next_session_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            t.episode('avsnitt208', NOTEWORTHY)
            self._scaffold(Path(tmp))
            new_dir = Path(tmp) / f'session_27_{date.today().isoformat()}'
            self.assertTrue((new_dir / 'sources').is_dir())
            self.assertTrue((new_dir / 'kortisar').is_dir())
            self.assertTrue((new_dir / 'avsnittXX27').is_dir())
            md = (new_dir / f'{new_dir.name}.md').read_text(encoding='utf-8')
            self.assertIn(f'# Session 27 - {date.today().isoformat()}', md)
            self.assertIn('* Prism Launcher 9.2', md)
            self.assertIn('  * Faithful 32x', md)
            self.assertIn('### avsnittXX27', md)
            self.assertIn('**Titel:**', md)

    def test_prompted_date_and_software_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            answers = (
                ['2026-08-01']                     # date
                + ['Prism Launcher 9.3']           # replace first software line
                + [''] * (len(kc.SOFTWARE_DEFAULTS) - 1)  # keep the rest
                + ['Handbrake 1.7', '']            # one extra line, then finish
            )
            self._scaffold(Path(tmp), answers)
            new_dir = Path(tmp) / 'session_27_2026-08-01'
            md = (new_dir / f'{new_dir.name}.md').read_text(encoding='utf-8')
            self.assertIn('# Session 27 - 2026-08-01', md)
            self.assertIn('* Prism Launcher 9.3', md)
            self.assertNotIn('Prism Launcher 9.2', md)
            self.assertIn('* OBS 23.0.3', md)
            self.assertIn('* Handbrake 1.7', md)

    def test_invalid_date_reprompted(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            answers = (
                ['nyss', '2026-08-02']
                + [''] * len(kc.SOFTWARE_DEFAULTS)
                + ['']
            )
            out = self._scaffold(Path(tmp), answers)
            self.assertIn('invalid date', out)
            self.assertTrue((Path(tmp) / 'session_27_2026-08-02').is_dir())

    def test_works_from_inside_session_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            t.episode('avsnitt207', NOTEWORTHY)
            self._scaffold(t.dir)
            self.assertTrue((Path(tmp) / f'session_27_{date.today().isoformat()}').is_dir())


class DiscoveryTests(unittest.TestCase):

    def test_walks_up_from_episode_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = SessionTree(tmp)
            ep = t.episode('avsnitt207', NOTEWORTHY)
            self.assertEqual(kc._discover(ep), [t.dir])

    def test_finds_session_children_naturally_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = SessionTree(tmp, 'session_9_2025-01-01')
            b = SessionTree(tmp, 'session_10_2025-02-01')
            self.assertEqual(kc._discover(Path(tmp)), [a.dir, b.dir])

    def test_session_dir_detected_by_md_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / 'somewhere'
            d.mkdir()
            (d / 'session_1_2025-01-01.md').write_text('# x\n', encoding='utf-8')
            self.assertEqual(kc._discover(d), [d])


if __name__ == '__main__':
    unittest.main()
