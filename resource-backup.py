#!/usr/bin/env python3

import subprocess
import yaml, json
import os, sys

# utils function to execute shell command
def run_shell_command(command_array):
  executed_command = subprocess.Popen(command_array, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
  executed_command.wait()
  command_stdout = str(executed_command.communicate()[0].decode("utf_8").strip())
  command_rc = int(executed_command.returncode)
  return [command_rc, command_stdout]

### VARIABLES TO CONFIGURE
# path to the yaml file with the resource to backup
resource_file_path = "resources.yaml"
## backup folder will be formed like this: backup_base_path + project_name + cluster_env_resource_dir
# base path for the backup directories
backup_base_path = "/opt/kup-manifest-backup"
# directory name for the resources to backup
cluster_env_resource_dir = "manifest/"
## openshift cluster variables
cluster_username = "change-me"
cluster_password = "change-me"
cluster_url = "https://api.clustername.example.com:6443"

backup_base_command = ["oc", "get"]
backup_tail_command = ["--output", "yaml"]

# get oc command full path
oc_full_path_result = run_shell_command(["which", "oc"])
if not oc_full_path_result[0] == 0:
  print("ERROR: No oc command found. Exiting...")
  sys.exit(10)
oc_full_path = oc_full_path_result[1]

# try to login to the cluster
login_command=[oc_full_path, "login", cluster_url, "--username", cluster_username, "--password", cluster_password]
login_result = run_shell_command(login_command)

# if login fails, exit
if login_result[0] != 0:
  print("ERROR: Unable to login to the cluster, see error below")
  print(login_result[1])
  sys.exit(20)

# open and parse the resources file
with open(resource_file_path, 'r') as resource_file:
  resources_to_backup = yaml.safe_load(resource_file)

# loop all the app parsed
for ocp_app in resources_to_backup.keys():
  # create project manifest destination folder
  ocp_backup_folder = str(backup_base_path) + "/" + str(resources_to_backup[ocp_app]["folder"]) + "/" + cluster_env_resource_dir
  if not os.path.exists(ocp_backup_folder):
    os.makedirs(ocp_backup_folder)

  print("")
  print("Starting backup of " + str(ocp_app) + " in " + str(ocp_backup_folder))

  # check if project exist on the cluster
  switch_namespace_command = [oc_full_path, "project", ocp_app]
  switch_namespace_result = run_shell_command(switch_namespace_command)

  # if project does not exist, skip to the next one
  if switch_namespace_result[0] != 0:
    print("WARNING: Unable to find app " + str(ocp_app) + ", see error below")
    print(switch_namespace_result[1])
    continue

  # get list of resources to backup
  ocp_app_resources = resources_to_backup[ocp_app]["resources"]

  # create the resource tuples type-name
  resources_to_get = []
  # loop all the resources
  for resource in ocp_app_resources:
    # if the resource is a list, loop all the elements
    if isinstance(resource, dict):
      resource_type = list(resource.keys())[0]
      # create n tuples with the same type and the specified name
      for resource_name in resource[resource_type]:
        resource_command = [str(resource_type), str(resource_name)]
        resources_to_get.append(resource_command)
      continue
    
    # if not a list, use the project name as resource tuple name
    resource_command = [str(resource), str(ocp_app)]
    resources_to_get.append(resource_command)

  # get all the resources
  for single_resource in resources_to_get:
    # concatenate the string to form the full command
    concatenated_backup_command = []
    concatenated_backup_command.extend(backup_base_command)
    concatenated_backup_command.extend(single_resource)
    concatenated_backup_command.extend(backup_tail_command)
    # run the command and retrieve the manifest output as a yaml
    backup_command_result = run_shell_command(concatenated_backup_command)
    resource_manifest = yaml.safe_load(backup_command_result[1])
    
    # clean the resources garbage data present in status and metadata child
    if "status" in resource_manifest.keys():
      del resource_manifest["status"]

    if "uid" in resource_manifest["metadata"].keys():
      del resource_manifest["metadata"]["uid"]

    if "selfLink" in resource_manifest["metadata"].keys():
      del resource_manifest["metadata"]["selfLink"]

    if "generation" in resource_manifest["metadata"].keys():
      del resource_manifest["metadata"]["generation"]
    
    if "managedFields" in resource_manifest["metadata"].keys():
      del resource_manifest["metadata"]["managedFields"]
    
    if "resourceVersion" in resource_manifest["metadata"].keys():
      del resource_manifest["metadata"]["resourceVersion"]
    
    if "creationTimestamp" in resource_manifest["metadata"].keys():
      del resource_manifest["metadata"]["creationTimestamp"]

    if "labels" in resource_manifest["metadata"].keys():
      if "kustomize.generated.resources" in resource_manifest["metadata"]["labels"].keys():
        del resource_manifest["metadata"]["labels"]["kustomize.generated.resources"]

    if "annotations" in resource_manifest["metadata"].keys():
      if "deployment.kubernetes.io/revision" in resource_manifest["metadata"]["annotations"].keys():
        del resource_manifest["metadata"]["annotations"]["deployment.kubernetes.io/revision"]
    
      if "kubectl.kubernetes.io/last-applied-configuration" in resource_manifest["metadata"]["annotations"].keys():
        del resource_manifest["metadata"]["annotations"]["kubectl.kubernetes.io/last-applied-configuration"]

    if "spec" in resource_manifest.keys():
      if "template" in resource_manifest["spec"].keys():
        if "metadata" in resource_manifest["spec"]["template"].keys():
          if "annotations" in resource_manifest["spec"]["template"]["metadata"].keys():
            if "kubectl.kubernetes.io/restartedAt" in resource_manifest["spec"]["template"]["metadata"]["annotations"].keys():
              del resource_manifest["spec"]["template"]["metadata"]["annotations"]["kubectl.kubernetes.io/restartedAt"]

    # pretty format the yaml manifest
    pretty_yaml_manifest = yaml.dump(resource_manifest)
    resource_tail_name = ""
    # generate manifest name
    if str(ocp_app) != str(single_resource[1]):
      resource_tail_name = "-" + str(single_resource[1])
    manifest_name = str(ocp_backup_folder) + "/" + str(ocp_app) + "-" + str(single_resource[0] + str(resource_tail_name) + ".yaml")
    print(manifest_name)
    # write the manifest to the file
    with open(manifest_name, 'w') as manifest_file:
      print(pretty_yaml_manifest, file = manifest_file)

# logout from the cluster
logout_command=[oc_full_path, "logout"]
logout_result = run_shell_command(logout_command)
