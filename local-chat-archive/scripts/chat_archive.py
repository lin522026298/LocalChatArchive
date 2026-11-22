"""Account-bound, local-only chat search and verified attachment retrieval."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import tempfile


class Refusal(ValueError):
    pass


def local(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or str(path).startswith(('\\\\','//')) or (
        os.name=='nt' and not re.fullmatch('[A-Za-z]:',path.drive)):
        raise Refusal('absolute_local_path_required')
    for part in (path,*path.parents):
        if os.path.lexists(part) and (part.is_symlink() or getattr(part.lstat(),'st_file_attributes',0)&0x400):
            raise Refusal('linked_path_refused')
    return path.resolve()


def target(profile, name):
    folder = local(profile['export_dir'])
    if not name or name!=name.strip() or name.endswith('.') or len(name)>120 or PureWindowsPath(name).is_reserved() or any(
            ord(c)<32 or c in '/\\<>:"|?*' for c in name):
        raise Refusal('safe_output_filename_required')
    path = local(folder/name)
    if not folder.is_dir() or path.parent!=folder or os.path.lexists(path):
        raise Refusal('output_folder_unavailable_or_file_already_exists')
    return path


def invoke(command, *, cwd=None, timeout=60, env=None):
    child = subprocess.run(command,cwd=cwd,stdin=subprocess.DEVNULL,capture_output=True,
        encoding='utf-8',errors='replace',timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=env)
    return child


def qq_call(settings, state, op, params):
    core = local(settings['core'])
    if not core.is_file():raise Refusal('qq_core_not_installed')
    with tempfile.TemporaryDirectory(prefix='local-chat-query-') as temp:
        args,report = Path(temp)/'arguments.json',Path(temp)/'result.json'
        args.write_text(json.dumps(params,ensure_ascii=False),encoding='utf-8')
        run = invoke([str(core),'--state',str(state),'--report',str(report),'agent','call',op,
            '--arguments-file',str(args)],cwd=core.parent)
        if run.returncode or not report.is_file():
            raise Refusal('qq_archive_read_failed_check_selected_account_and_archive_availability')
        return json.loads(report.read_text('utf-8-sig'))


def qq_items(links, state):
    for item in links:
        primary = item.get('primary') or {}
        value = {k:item.get(k) for k in ('filename','media_type','verification','role','note')}
        value['segment'] = item.get('segment_index')
        value['status'] = 'candidate_or_unavailable'
        if (item.get('verification') in {'verified','verified_exact','verified_hash','verified_content'} and
                item.get('role')=='primary' and primary.get('path')):
            path = local(primary['path'])
            # QQ's verified object layouts use a digest basename, optionally
            # with an extension. Never substitute a thumbnail or candidate.
            expected = path.name.split('.')[0]
            if not path.is_relative_to(state) or not path.is_file():
                value['status'] = 'original_missing_or_outside_selected_archive'
            elif not re.fullmatch('[0-9a-f]{64}',expected):
                value['status'] = 'verified_association_but_no_addressed_original_digest'
            else:
                value.update(status='verified_original',sha256=expected)
                yield value,path
                continue
        yield value,None


def copy_qq(src, dest, sha):
    created = None
    try:
        digest = hashlib.sha256(); size = 0
        with src.open('rb') as original,dest.open('xb') as output:
            created = os.fstat(output.fileno())
            while block := original.read(1024**2):
                digest.update(block);size += len(block);output.write(block)
        with dest.open('rb') as output:
            if digest.hexdigest()!=sha or hashlib.file_digest(output,'sha256').hexdigest()!=sha:
                raise Refusal('attachment_hash_mismatch')
        return dict(path=str(dest),bytes=size,sha256=sha,verified=True,automatically_opened=False)
    except BaseException:
        if created is not None and dest.exists() and os.path.samestat(created,dest.lstat()):
            dest.unlink()
        raise


def qq(profile, args):
    settings = profile['qq'];state = local(settings['state'])
    call = lambda op, params: qq_call(settings,state,op,params)
    if args.operation=='accounts':
        fields = {'account_key','account_label','account_id','display_id','display_name','self_qq',
                  'c2c_messages','group_messages','first_timestamp','last_timestamp','timeline_start','timeline_end'}
        rows = [{k:v for k,v in row.items() if k in fields and isinstance(v,(str,int,type(None)))}
                | {'account':row['account_key']} for row in call('accounts',{})]
        return dict(rows=rows,scope='published_local_archive_not_login_state')
    public = dict(account=args.account)
    cols = ('msg_id','timestamp','direction','sender_label','sender_qq','text','source_table','msg_type','content_type')
    narrow = lambda rows:[{k:r[k] for k in cols if k in r} for r in rows]
    if args.operation=='conversations':
        rows = call('conversations',dict(public,query=args.query or ''))
        end = args.offset+args.limit
        return dict(rows=rows[args.offset:end],next_offset=end if end<len(rows) else None)
    if args.operation=='search':
        if len(args.query.strip())<2:raise Refusal('qq_search_requires_at_least_two_characters')
        rows = call('search',dict(public,query=args.query,limit=args.limit,offset=args.offset))
        visible = [r for r in rows if not args.conversation or r['conversation']['key']==args.conversation]
        return dict(rows=visible,next_offset=args.offset+args.limit if len(rows)==args.limit else None)
    if args.operation=='messages':
        if args.offset:raise Refusal('qq_messages_use_context_or_native_cursor_not_offset')
        return dict(rows=narrow(call('messages' if args.conversation else 'timeline',
            dict(public,limit=args.limit,**({'conversation':args.conversation} if args.conversation else {})))))
    if re.fullmatch(r'-?\d{1,19}',args.id) is None or not -(1<<63)<=int(args.id)<(1<<63):
        raise Refusal('qq_message_id_must_be_an_exact_decimal_string')
    if args.operation=='context':
        rows = call('messages',dict(public,conversation=args.conversation,around=args.id,limit=args.limit))
        if not any(r.get('msg_id')==args.id for r in rows):raise Refusal('message_not_found_in_selected_conversation')
        # Raw native fields and filesystem metadata are only needed for detail.
        return dict(anchor=args.id,rows=narrow(rows))
    if args.operation=='detail':
        return dict(observations=call('observations',dict(public,msg_id=args.id)))
    media = call('media',dict(public,msg_id=args.id,source_table=args.table))
    media = [r for r in media if str(r.get('msg_id'))==args.id and r.get('source_table')==args.table]
    items = list(qq_items(media,state))
    if args.operation=='attachments':
        return dict(items=[r for r,_ in items],scope='selected_account_message_and_table_only')
    paths = {p for r,p in items if p is not None and r['segment']==args.segment and r['sha256']==args.sha}
    if not paths:raise Refusal('verified_original_not_found_for_this_message_segment')
    dest = target(profile,args.name)
    if dest.is_relative_to(state):raise Refusal('output_must_be_outside_archive')
    return copy_qq(sorted(paths)[0],dest,args.sha)


def wechat(profile, args):
    conf=profile['wechat']
    root,python,cwd = (local(conf[key]) for key in ('root','python','source_dir'))
    command = [str(python),'-m','wechat_capture_next.agent_archive','--root',str(root),args.operation]
    for field in ('account','query','id','limit','offset','conversation','sender','message_type','since','until',
                  'after_file','after_image','kind','sha','expected_md5'):
        value=getattr(args,field,None)
        if value is not None:command.extend(('--'+field.replace('_','-'),str(value)))
    if args.operation=='export':command.extend(('--out',str(target(profile,args.name))))
    run=invoke(command,cwd=cwd,timeout=150,env=dict(os.environ,PYTHONPATH=str(cwd),PYTHONDONTWRITEBYTECODE='1'))
    try:
        result=json.loads(run.stdout)
    except ValueError:
        raise Refusal('wechat_reader_unavailable_check_runtime_and_source_checkout') from None
    if isinstance(result,dict) and 'reason' in result and run.returncode:
        raise Refusal(result['reason'])
    if run.returncode:raise Refusal('wechat_archive_read_failed')
    return result['result']


def parse():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,default=Path(__file__).resolve().parents[1]/'local.private.json')
    platforms=parser.add_subparsers(dest='platform',required=True)
    for platform in ('qq','wechat'):
        sub=platforms.add_parser(platform).add_subparsers(dest='operation',required=True)
        for op in ('accounts','conversations','search','messages','context','detail','attachments','export'):
            p=sub.add_parser(op)
            if op!='accounts':p.add_argument('--account',required=True)
            if op in ('conversations','search','messages','context','detail','attachments'):
                p.add_argument('--limit',type=int,default=20);p.add_argument('--offset',type=int,default=0)
            if op in ('conversations','search') or (platform=='wechat' and op=='messages'):
                p.add_argument('--query',required=op=='search')
            if op in ('search','messages') or (platform=='qq' and op=='context'):
                p.add_argument('--conversation',required=op=='context')
            if platform=='wechat' and op in ('search','messages'):
                for field in ('sender','message-type','since','until'):p.add_argument('--'+field)
            if op in ('context','detail','attachments','export'):p.add_argument('--id',required=True)
            if platform=='wechat' and op=='attachments':
                p.add_argument('--after-file',default='');p.add_argument('--after-image',default='')
            if platform=='qq' and op in ('attachments','export'):
                p.add_argument('--table',choices=('c2c_messages','group_messages'),required=True)
            if op=='export':
                p.add_argument('--name',required=True);p.add_argument('--sha',required=True)
                if platform=='qq':p.add_argument('--segment',type=int,required=True)
                else:
                    p.add_argument('--kind',choices=('file','video','voice','image'),required=True)
                    p.add_argument('--expected-md5')
    return parser.parse_args()


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    args=parse(); account=getattr(args,'account',None)
    try:
        if account is not None and (not account.strip() or len(account)>200 or any(ord(c)<32 for c in account)):
            raise Refusal('explicit_account_required')
        if hasattr(args,'limit') and not(1<=args.limit<=100 and 0<=args.offset<=100000):raise Refusal('invalid_page')
        if getattr(args,'query',None) is not None and len(args.query)>1000:raise Refusal('query_too_long')
        if args.operation=='export' and not re.fullmatch('[0-9a-f]{64}',args.sha):raise Refusal('invalid_attachment_hash')
        profile=json.loads(local(args.profile.absolute()).read_text('utf-8-sig'))
        if args.platform not in profile:raise Refusal('selected_platform_not_configured')
        result=(qq if args.platform=='qq' else wechat)(profile,args)
        print(json.dumps(dict(platform=args.platform,account=account,operation=args.operation,result=result),ensure_ascii=False))
        return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        print(json.dumps(dict(platform=args.platform,error_type=type(error).__name__,
            reason=str(error) if isinstance(error,Refusal) else 'local_profile_archive_or_operation_unavailable')))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
