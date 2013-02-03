#!/usr/bin/env python
# Programmer: Chris Bunch (chris@appscale.com)


# General-purpose Python library imports
import time


# AppScale-specific imports
from appcontroller_client import AppControllerClient
from appscale_logger import AppScaleLogger
from custom_exceptions import AppScaleException
from custom_exceptions import BadConfigurationException
from local_state import APPSCALE_VERSION
from local_state import LocalState
from node_layout import NodeLayout
from remote_helper import RemoteHelper
from user_app_client import UserAppClient


class AppScaleTools():
  """AppScaleTools provides callers with a way to start, stop, and interact
  with AppScale deployments, on virtualized clusters or on cloud
  infrastructures.

  These methods provide an interface for users who wish to start and control
  AppScale through a dict of parameters. An alternative to this method is to
  use the AppScale class, which stores state in an AppScalefile in the
  current working directory (as opposed to a dict), but under the hood these
  methods get called anyways.
  """

  
  @classmethod
  def remove_app(cls, options):
    """Instructs AppScale to no longer host the named application.

    Args:
      options: A Namespace that has fields for each parameter that can be
        passed in via the command-line interface.
    """
    if not options.confirm:
      response = raw_input("Are you sure you want to remove this application? ")
      if response != 'yes' and response != 'y':
        raise AppScaleException("Cancelled application removal.")

    """
    result = CommonFunctions.confirm_app_removal(options['confirm'],
      options['appname'])
    if result == "NO"
      raise AppScaleException.new(APP_REMOVAL_CANCELLED)
    end

    CommonFunctions.remove_app(options['appname'], options['keyname'])
    secret_key = CommonFunctions.get_secret_key(keyname)
    head_node_ip = CommonFunctions.get_head_node_ip(keyname)
    acc = AppControllerClient.new(head_node_ip, secret_key)
    userappserver_ip = acc.get_userappserver_ip()

    uac = UserAppClient.new(userappserver_ip, secret_key)
    app_exists = uac.does_app_exist?(app_name, retry_on_except=true)

    if !app_exists
      raise AppEngineConfigException.new(AppScaleTools::APP_NOT_RUNNING)
    end

    load_balancer_ip = CommonFunctions.get_load_balancer_ip(keyname)
    acc.stop_app(app_name)

    Kernel.puts "Please wait for your app to shut down."
    loop {
      if !acc.app_is_running?(app_name)
        break
      end
      Kernel.sleep(5)
    }
    Kernel.puts "Done shutting down app #{options['appname']}"
  end
    """


  @classmethod
  def run_instances(cls, options):
    """Starts a new AppScale deployment with the parameters given.

    Args:
      options: A Namespace that has fields for each parameter that can be
        passed in via the command-line interface.
    Raises:
      BadConfigurationException: If the user passes in options that are not
        sufficient to start an AppScale deplyoment (e.g., running on EC2 but
        not specifying the AMI to use), or if the user provides us
        contradictory options (e.g., running on EC2 but not specifying EC2
        credentials).
    """
    LocalState.make_appscale_directory()
    LocalState.ensure_appscale_isnt_running(options.keyname, options.force)

    if options.infrastructure:
      AppScaleLogger.log("Starting AppScale " + APPSCALE_VERSION +
        " over the " + options.infrastructure + " cloud.")
    else:
      AppScaleLogger.log("Starting AppScale " + APPSCALE_VERSION +
        " over a virtualized cluster.")

    AppScaleLogger.remote_log_tools_state(options, "started")
    time.sleep(2)

    node_layout = NodeLayout(options)
    if not node_layout.is_valid():
      raise BadConfigurationException("There were errors with your " + \
        "placement strategy:\n{0}".format(str(node_layout.errors())))

    if not node_layout.is_supported():
      AppScaleLogger.warn("Warning: This deployment strategy is not " + \
        "officially supported.")
      time.sleep(1)

    public_ip, instance_id = RemoteHelper.start_head_node(options, node_layout)
    AppScaleLogger.log("\nPlease wait for AppScale to prepare your machines " +
      "for use.")

    # Write our metadata as soon as possible to let users SSH into those
    # machines via 'appscale ssh'
    LocalState.update_local_metadata(options, node_layout, public_ip,
      instance_id)
    RemoteHelper.copy_local_metadata(public_ip, options.keyname,
      options.verbose)

    acc = AppControllerClient(public_ip, LocalState.get_secret_key(
      options.keyname))
    uaserver_host = acc.get_uaserver_host(options.verbose)
    RemoteHelper.sleep_until_port_is_open(public_ip, UserAppClient.PORT,
      options.verbose)

    # Update our metadata again so that users can SSH into other boxes that
    # may have been started.
    LocalState.update_local_metadata(options, node_layout, public_ip,
      instance_id)
    RemoteHelper.copy_local_metadata(public_ip, options.keyname,
      options.verbose)

    AppScaleLogger.log("UserAppServer is at {0}".format(uaserver_host))

    uaserver_client = UserAppClient(uaserver_host,
      LocalState.get_secret_key(options.keyname))

    if 'admin_user' in options and 'admin_pass' in options:
      AppScaleLogger.log("Using the provided admin username/password")
      username, password = options.admin_user, options.admin_pass
    elif 'test' in options:
      AppScaleLogger.log("Using default admin username/password")
      username, password = LocalState.DEFAULT_USER, LocalState.DEFAULT_PASSWORD
    else:
      username, password = LocalState.get_credentials()

    RemoteHelper.create_user_accounts(username, password, uaserver_host,
      options.keyname)
    uaserver_client.set_admin_role(username)

    RemoteHelper.wait_for_machines_to_finish_loading(public_ip, options.keyname)
    # Finally, update our metadata once we know that all of the machines are
    # up and have started all their API services.
    LocalState.update_local_metadata(options, node_layout, public_ip,
      instance_id)
    RemoteHelper.copy_local_metadata(public_ip, options.keyname, options.verbose)

    AppScaleLogger.success("AppScale successfully started!")
    AppScaleLogger.success("View status information about your AppScale " + \
      "deployment at http://{0}/status".format(LocalState.get_login_host(
      options.keyname)))
    AppScaleLogger.remote_log_tools_state(options, "finished")
