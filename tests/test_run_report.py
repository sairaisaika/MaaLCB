"""The run report attributes program time to floors and pages and ranks the stops.

The numbers behind the public-version goal (30.6 / 20.4 / 31.0 / 31.4 / 33.3 minutes per
floor, battle animation taking four tenths of the time) were first produced by throwaway
scripts. This is the same arithmetic as a tested part of the project.
"""
from maalimbus import run_report


def at(seconds):
    return '2026-11-23T10:%02d:%02d+00:00' % divmod(seconds, 60)


def run(cleared, steps, stop=None, scope='a84a7162'):
    rows = [dict(event='mirror_loop_start', utc=at(0), run_scope=scope),
            dict(event='page_checkpoint', utc=at(0), progress=dict(cleared_floors=cleared))]
    clock = 0
    for page, seconds in steps:
        clock += seconds
        rows.append(dict(event='step_finished', utc=at(clock), page=page))
    if stop:
        rows.append(dict(event='mirror_loop_stopped', utc=at(clock + 1), reason=stop, clicks_sent=3, passed=False))
    return rows


def test_time_goes_to_the_floor_reached_and_the_page_of_the_last_step():
    one = run_report.run_time(run([1, 2], [('MAP', 10), ('BATTLE_HUD', 6), ('UNKNOWN', 30), ('SHOP', 20)]))
    assert one['floors'] == {3: 66.0} and one['scope'] == 'a84a7162'
    # A gap belongs to the page that was current while it ran: the step before it.
    assert one['pages'] == {'MAP': 6.0, 'BATTLE_HUD': 30.0, 'UNKNOWN': 20.0}
    assert one['battle'] == {3: 50.0}
    assert one['steps'] == {'MAP': 1, 'BATTLE_HUD': 1, 'UNKNOWN': 1, 'SHOP': 1}


def test_waiting_for_a_person_is_not_program_time():
    rows = run([], [('MAP', 10)])
    rows.append(dict(event='step_finished', utc=at(10 + 600), page='MAP'))
    assert run_report.run_time(rows)['floors'] == {1: 10.0}


def test_many_runs_become_one_report_with_ranked_stops():
    runs = [('pi-1', run([], [('MAP', 60), ('BATTLE_HUD', 60)], 'no_candidate_node_observed')),
            ('pi-2', run([1], [('MAP', 60), ('SHOP', 60), ('SHOP', 60)], 'no_candidate_node_observed')),
            ('pi-3', run([1], [('SHOP', 30)], 'Fresh refresh currency delta and complete changed shelf not proven')),
            ('pi-4', run([1], [('MAP', 30)], 'the_budget_could_not_pay_for_another_step')),
            ('pi-5', [])]
    report = run_report.combine(runs)
    assert report['runs'] == 4 and report['first'] == 'pi-1' and report['last'] == 'pi-4'
    assert [row['floor'] for row in report['floors']] == [1, 2]
    assert report['slowest_floor_minutes'] == max(row['minutes'] for row in report['floors'])
    # A bound the caller set is not a stop to fix.
    assert [(row['reason'], row['count']) for row in report['stops']] == [
        ('no_candidate_node_observed', 2),
        ('Fresh refresh currency delta and complete changed shelf not proven', 1)]
    assert report['stops'][0]['where'][0]['count'] == 1
    assert abs(sum(row['share'] for row in report['pages']) - 1) < .01


def test_the_report_names_runs_only_by_directory_name():
    rows = run([], [('MAP', 10)], 'x')
    rows.insert(1, dict(event='mirror_loop_start', utc=at(0), run_scope='a84a7162',
                        directory='D:\\\\somewhere\\\\private', data_directory='C:\\\\Users\\\\someone\\\\config'))
    text = '\n'.join(run_report.lines(run_report.combine([('pi-1', rows)])))
    assert 'somewhere' not in text and 'someone' not in text and 'pi-1' in text
