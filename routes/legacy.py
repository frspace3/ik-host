"""
Legacy Route Aliases Blueprint
Provides full backward compatibility for older API routes.
"""
from flask import Blueprint, redirect, request, url_for

legacy_bp = Blueprint('legacy_bp', __name__)

@legacy_bp.route('/servers', methods=['GET', 'POST'])
def legacy_servers():
    if request.method == 'POST':
        return redirect(url_for('servers_bp.add_srv'), code=307)
    return redirect(url_for('servers_bp.list_servers'))

@legacy_bp.route('/add', methods=['POST'])
def legacy_add():
    return redirect(url_for('servers_bp.add_srv'), code=307)

@legacy_bp.route('/server/action/<folder>/<act>', methods=['POST'])
def legacy_server_action(folder, act):
    return redirect(url_for('servers_bp.server_action', folder=folder, act=act), code=307)

@legacy_bp.route('/server/log/<folder>')
def legacy_server_log(folder):
    return redirect(url_for('servers_bp.server_log', folder=folder))

@legacy_bp.route('/server/set-startup/<folder>', methods=['POST'])
def legacy_set_startup(folder):
    return redirect(url_for('servers_bp.set_startup', folder=folder), code=307)

@legacy_bp.route('/server/set-auto-restart/<folder>', methods=['POST'])
def legacy_set_auto_restart(folder):
    return redirect(url_for('servers_bp.set_auto_restart', folder=folder), code=307)

@legacy_bp.route('/server/command/<folder>', methods=['POST'])
def legacy_server_command(folder):
    return redirect(url_for('servers_bp.server_command', folder=folder), code=307)

@legacy_bp.route('/server/delete/<folder>', methods=['POST'])
def legacy_delete_server(folder):
    return redirect(url_for('servers_bp.delete_server', folder=folder), code=307)

@legacy_bp.route('/server/download-zip/<folder>')
def legacy_download_server_zip(folder):
    return redirect(url_for('servers_bp.download_server_zip', folder=folder))

@legacy_bp.route('/server/rename/<folder>', methods=['POST'])
def legacy_rename_server(folder):
    return redirect(url_for('servers_bp.rename_server', folder=folder), code=307)

@legacy_bp.route('/server/deploy-pipeline/<folder>', methods=['POST'])
def legacy_deploy_pipeline(folder):
    return redirect(url_for('servers_bp.deploy_pipeline', folder=folder), code=307)

@legacy_bp.route('/server/detect-startup/<folder>')
def legacy_detect_startup(folder):
    return redirect(url_for('servers_bp.detect_startup', folder=folder))

@legacy_bp.route('/server/endpoints/<folder>')
def legacy_server_endpoints(folder):
    return redirect(url_for('servers_bp.server_endpoints', folder=folder))

@legacy_bp.route('/server/sync-install/<folder>', methods=['POST'])
def legacy_sync_install(folder):
    return redirect(url_for('servers_bp.sync_install', folder=folder), code=307)

@legacy_bp.route('/files/list/<folder>')
def legacy_flist(folder):
    return redirect(url_for('files_bp.flist', folder=folder, **request.args))

@legacy_bp.route('/files/read/<folder>')
def legacy_fread(folder):
    return redirect(url_for('files_bp.fread', folder=folder, **request.args))

@legacy_bp.route('/files/save/<folder>', methods=['POST'])
def legacy_fsave(folder):
    return redirect(url_for('files_bp.fsave', folder=folder), code=307)

@legacy_bp.route('/files/delete-bulk/<folder>', methods=['POST'])
def legacy_delete_bulk(folder):
    return redirect(url_for('files_bp.delete_bulk', folder=folder), code=307)

@legacy_bp.route('/files/create-file/<folder>', methods=['POST'])
def legacy_create_file(folder):
    return redirect(url_for('files_bp.create_file_route', folder=folder), code=307)

@legacy_bp.route('/files/create-folder/<folder>', methods=['POST'])
def legacy_create_folder(folder):
    return redirect(url_for('files_bp.create_folder_route', folder=folder), code=307)

@legacy_bp.route('/files/upload/<folder>', methods=['POST'])
def legacy_upload_file(folder):
    return redirect(url_for('files_bp.upload_file', folder=folder), code=307)

@legacy_bp.route('/files/rename/<folder>', methods=['POST'])
def legacy_rename_file(folder):
    return redirect(url_for('files_bp.rename_file', folder=folder), code=307)

@legacy_bp.route('/files/download/<folder>/<name>')
def legacy_download_file(folder, name):
    return redirect(url_for('files_bp.download_file', folder=folder, name=name, **request.args))

@legacy_bp.route('/files/zip-bulk/<folder>', methods=['POST'])
def legacy_zip_bulk(folder):
    return redirect(url_for('files_bp.zip_bulk', folder=folder), code=307)

@legacy_bp.route('/files/unzip/<folder>', methods=['POST'])
def legacy_unzip_file(folder):
    return redirect(url_for('files_bp.unzip_file', folder=folder), code=307)

@legacy_bp.route('/files/copy-bulk/<folder>', methods=['POST'])
def legacy_copy_bulk(folder):
    return redirect(url_for('files_bp.copy_bulk', folder=folder), code=307)

@legacy_bp.route('/files/move-bulk/<folder>', methods=['POST'])
def legacy_move_bulk(folder):
    return redirect(url_for('files_bp.move_bulk', folder=folder), code=307)

@legacy_bp.route('/api/report-hack/<folder>', methods=['POST'])
def legacy_report_hack(folder):
    return redirect(url_for('servers_bp.report_hack', folder=folder), code=307)

@legacy_bp.route('/admin/stats')
def legacy_admin_stats():
    return redirect(url_for('admin_bp.admin_stats'))

@legacy_bp.route('/admin/user/update', methods=['POST'])
@legacy_bp.route('/admin/users/update', methods=['POST'])
def legacy_admin_users_update():
    return redirect(url_for('admin_bp.update_user'), code=307)

@legacy_bp.route('/admin/users/bulk-limit', methods=['POST'])
def legacy_admin_users_bulk_limit():
    return redirect(url_for('admin_bp.bulk_limit_users'), code=307)

@legacy_bp.route('/admin/send-warning', methods=['POST'])
def legacy_admin_send_warning():
    return redirect(url_for('admin_bp.send_warning'), code=307)

@legacy_bp.route('/admin/set-popup', methods=['POST'])
def legacy_admin_set_popup():
    return redirect(url_for('admin_bp.set_popup'), code=307)

@legacy_bp.route('/admin/create-user', methods=['POST'])
@legacy_bp.route('/admin/users/create', methods=['POST'])
def legacy_admin_create_user():
    return redirect(url_for('admin_bp.admin_create_user'), code=307)

@legacy_bp.route('/admin/user/delete/<int:uid>', methods=['POST'])
@legacy_bp.route('/admin/users/<int:uid>/delete', methods=['POST'])
def legacy_admin_delete_user(uid):
    return redirect(url_for('admin_bp.delete_user', uid=uid), code=307)

@legacy_bp.route('/admin/suspend-server/<int:sid>', methods=['POST'])
@legacy_bp.route('/admin/servers/<int:sid>/suspend', methods=['POST'])
def legacy_admin_suspend_server(sid):
    return redirect(url_for('admin_bp.admin_suspend_server', sid=sid), code=307)

@legacy_bp.route('/admin/delete-server/<int:sid>', methods=['POST'])
@legacy_bp.route('/admin/servers/<int:sid>/delete', methods=['POST'])
def legacy_admin_delete_server(sid):
    return redirect(url_for('admin_bp.admin_delete_server', sid=sid), code=307)

@legacy_bp.route('/ticket/create', methods=['POST'])
def legacy_ticket_create():
    return redirect(url_for('auth_bp.create_ticket'), code=307)

@legacy_bp.route('/announcement')
def legacy_announcement():
    return redirect(url_for('auth_bp.get_announcement'))

