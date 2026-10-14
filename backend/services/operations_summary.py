"""Observed workflow metrics, bounded to the caller's recent run sample."""
from collections import Counter
from datetime import datetime, timezone
from statistics import median


def parse_time(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (TypeError, ValueError):
        return None


def summarize_runs(runs, user_id):
    runs = [r for r in runs if r.get('user_id') == user_id]
    counts = Counter(r.get('status', 'UNKNOWN') for r in runs)
    durations, failures, attention = [], Counter(), []
    now = datetime.now(timezone.utc)
    for run in runs:
        started = parse_time(run.get('created_at'))
        completed_times = []
        tasks = run.get('tasks') or []
        for task in tasks:
            if task.get('status') == 'FAILED':
                failures[task.get('agent') or 'unknown'] += 1
            ended = parse_time(task.get('completed_at'))
            if ended:
                completed_times.append(ended)
        if run.get('status') == 'COMPLETED' and started and completed_times:
            durations.append(max(0, (max(completed_times) - started).total_seconds()))
        waiting = any(t.get('status') == 'WAITING_APPROVAL' for t in tasks)
        age = max(0, (now - started).total_seconds()) if started else None
        if waiting or run.get('status') == 'FAILED' or (
            run.get('status') in ('RUNNING', 'PENDING', 'WAITING') and age is not None and age > 900
        ):
            attention.append({'run_id': run['run_id'], 'status': run.get('status'),
                              'reason': 'approval_required' if waiting else 'failed' if run.get('status') == 'FAILED' else 'long_running',
                              'age_seconds': age})
    completed = counts['COMPLETED']
    failed = counts['FAILED']
    return {
        'sample_size': len(runs), 'sample_limit': 200, 'status_counts': dict(counts),
        'completion_rate': round(completed / (completed + failed) * 100, 1) if completed + failed else None,
        'median_completion_seconds': round(median(durations), 1) if durations else None,
        'failed_tasks_by_agent': dict(failures), 'attention': attention,
        'generated_at': now.isoformat(),
        'cost_tracking': 'not_available',
    }
