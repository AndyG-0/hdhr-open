#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Script to generate a clean, modern HDHROpen.xcodeproj
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR / "HDHROpen.xcodeproj"
PROJECT_FILE = PROJECT_DIR / "project.pbxproj"
SCHEMES_DIR = PROJECT_DIR / "xcshareddata" / "xcschemes"

PROJECT_DIR.mkdir(parents=True, exist_ok=True)
SCHEMES_DIR.mkdir(parents=True, exist_ok=True)

# Generate stable IDs
def gid(name: str) -> str:
    import hashlib
    return hashlib.md5(name.encode('utf-8')).hexdigest()[:24].upper()

# Scan files
def scan_files(directory: Path):
    files = []
    for root, dirs, filenames in os.walk(directory):
        # Don't descend into asset catalogs - they're referenced as a single
        # folder reference, not scanned file-by-file.
        dirs[:] = [d for d in dirs if not d.endswith('.xcassets')]
        for f in filenames:
            if f.endswith('.swift') or f.endswith('.plist') or f.endswith('.entitlements'):
                p = Path(root) / f
                rel = p.relative_to(BASE_DIR)
                files.append(rel)
    return sorted(files)

def scan_asset_catalogs(directory: Path):
    catalogs = []
    for root, dirs, _ in os.walk(directory):
        for d in list(dirs):
            if d.endswith('.xcassets'):
                p = Path(root) / d
                rel = p.relative_to(BASE_DIR)
                catalogs.append(rel)
                dirs.remove(d)  # don't recurse into it
    return sorted(catalogs)

tv_files = scan_files(BASE_DIR / "HDHROpenTV")
ios_files = scan_files(BASE_DIR / "HDHROpeniOS")
ios_test_files = scan_files(BASE_DIR / "HDHROpeniOSTests")
tv_test_files = scan_files(BASE_DIR / "HDHROpenTVTests")
tv_catalogs = scan_asset_catalogs(BASE_DIR / "HDHROpenTV")
ios_catalogs = scan_asset_catalogs(BASE_DIR / "HDHROpeniOS")

# PBX objects
file_refs = []
build_files = []

def add_swift_sources(files):
    """Emit PBXFileReference/PBXBuildFile entries for .swift/.plist/.entitlements
    files and return the PBXBuildFile ids for the .swift files (for Sources
    build phase membership)."""
    ids = []
    for f in files:
        f_id = gid(f"file_{f}")
        b_id = gid(f"build_{f}")
        name = f.name
        if f.suffix == '.swift':
            file_refs.append(f'\t\t{f_id} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = "{name}"; sourceTree = "<group>"; }};')
            build_files.append(f'\t\t{b_id} /* {name} in Sources */ = {{isa = PBXBuildFile; fileRef = {f_id} /* {name} */; }};')
            ids.append(b_id)
        elif f.suffix == '.plist':
            file_refs.append(f'\t\t{f_id} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = "{name}"; sourceTree = "<group>"; }};')
        elif f.suffix == '.entitlements':
            file_refs.append(f'\t\t{f_id} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = text.plist.entitlements; path = "{name}"; sourceTree = "<group>"; }};')
    return ids

tv_sources = add_swift_sources(tv_files)
ios_sources = add_swift_sources(ios_files)
ios_test_sources = add_swift_sources(ios_test_files)
tv_test_sources = add_swift_sources(tv_test_files)

tv_resources = []
ios_resources = []

for f in tv_catalogs:
    f_id = gid(f"file_{f}")
    b_id = gid(f"build_{f}")
    name = f.name
    file_refs.append(f'\t\t{f_id} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = folder.assetcatalog; path = "{name}"; sourceTree = "<group>"; }};')
    build_files.append(f'\t\t{b_id} /* {name} in Resources */ = {{isa = PBXBuildFile; fileRef = {f_id} /* {name} */; }};')
    tv_resources.append(b_id)

for f in ios_catalogs:
    f_id = gid(f"file_{f}")
    b_id = gid(f"build_{f}")
    name = f.name
    file_refs.append(f'\t\t{f_id} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = folder.assetcatalog; path = "{name}"; sourceTree = "<group>"; }};')
    build_files.append(f'\t\t{b_id} /* {name} in Resources */ = {{isa = PBXBuildFile; fileRef = {f_id} /* {name} */; }};')
    ios_resources.append(b_id)

# Groups hierarchy
def build_group_tree(files, base_name):
    # build a nested dictionary
    tree = {}
    for f in files:
        parts = f.parts  # e.g. ('HDHROpenTV', 'Views', 'Guide', 'TVGuideView.swift')
        curr = tree
        for part in parts[1:]: # skip root folder name
            curr = curr.setdefault(part, {})

    # render PBXGroup blocks
    groups_out = []

    def render_node(node, path_prefix, group_name):
        children = []
        sub_groups = []
        for k, v in node.items():
            if v: # is a directory
                sub_path = f"{path_prefix}/{k}" if path_prefix else k
                sub_id = gid(f"group_{base_name}_{sub_path}")
                children.append(f"{sub_id} /* {k} */")
                sub_groups.append((v, sub_path, k))
            else: # is a file
                f_path = f"{base_name}/{path_prefix}/{k}" if path_prefix else f"{base_name}/{k}"
                f_id = gid(f"file_{f_path}")
                children.append(f"{f_id} /* {k} */")

        my_id = gid(f"group_{base_name}_{path_prefix}") if path_prefix else gid(f"group_{base_name}")
        children_str = ",\n\t\t\t\t".join(children)
        path_attr = f'path = "{group_name}"; ' if group_name else ""
        groups_out.append(f'''\t\t{my_id} /* {group_name or base_name} */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{children_str},
\t\t\t);
\t\t\t{path_attr}sourceTree = "<group>";
\t\t}};''')
        for sub_v, sub_path, sub_k in sub_groups:
            render_node(sub_v, sub_path, sub_k)

    render_node(tree, "", base_name)
    return groups_out

tv_groups = build_group_tree(tv_files + tv_catalogs, "HDHROpenTV")
ios_groups = build_group_tree(ios_files + ios_catalogs, "HDHROpeniOS")
ios_test_groups = build_group_tree(ios_test_files, "HDHROpeniOSTests")
tv_test_groups = build_group_tree(tv_test_files, "HDHROpenTVTests")

# Product file references
tv_product_id = gid("product_tv")
ios_product_id = gid("product_ios")
ios_test_product_id = gid("product_ios_tests")
tv_test_product_id = gid("product_tv_tests")
file_refs.append(f'\t\t{tv_product_id} /* HDHROpenTV.app */ = {{isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = HDHROpenTV.app; sourceTree = BUILT_PRODUCTS_DIR; }};')
file_refs.append(f'\t\t{ios_product_id} /* HDHROpeniOS.app */ = {{isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = HDHROpeniOS.app; sourceTree = BUILT_PRODUCTS_DIR; }};')
file_refs.append(f'\t\t{ios_test_product_id} /* HDHROpeniOSTests.xctest */ = {{isa = PBXFileReference; explicitFileType = wrapper.cfbundle; includeInIndex = 0; path = HDHROpeniOSTests.xctest; sourceTree = BUILT_PRODUCTS_DIR; }};')
file_refs.append(f'\t\t{tv_test_product_id} /* HDHROpenTVTests.xctest */ = {{isa = PBXFileReference; explicitFileType = wrapper.cfbundle; includeInIndex = 0; path = HDHROpenTVTests.xctest; sourceTree = BUILT_PRODUCTS_DIR; }};')

# Package refs & product dependencies
pkg_ref_id = gid("local_pkg_ref_kit")
tv_pkg_dep_id = gid("tv_pkg_dep_kit")
ios_pkg_dep_id = gid("ios_pkg_dep_kit")
ios_test_pkg_dep_id = gid("ios_test_pkg_dep_kit")
tv_test_pkg_dep_id = gid("tv_test_pkg_dep_kit")

viewinspector_pkg_ref_id = gid("remote_pkg_ref_viewinspector")
ios_viewinspector_dep_id = gid("ios_pkg_dep_viewinspector")
tv_viewinspector_dep_id = gid("tv_pkg_dep_viewinspector")

# Build phases
tv_sources_phase_id = gid("tv_sources_phase")
ios_sources_phase_id = gid("ios_sources_phase")
ios_test_sources_phase_id = gid("ios_test_sources_phase")
tv_test_sources_phase_id = gid("tv_test_sources_phase")

tv_frameworks_phase_id = gid("tv_frameworks_phase")
ios_frameworks_phase_id = gid("ios_frameworks_phase")
ios_test_frameworks_phase_id = gid("ios_test_frameworks_phase")
tv_test_frameworks_phase_id = gid("tv_test_frameworks_phase")

tv_resources_phase_id = gid("tv_resources_phase")
ios_resources_phase_id = gid("ios_resources_phase")

tv_sources_entries = ",\n\t\t\t\t".join([f"{b_id} /* in Sources */" for b_id in tv_sources])
ios_sources_entries = ",\n\t\t\t\t".join([f"{b_id} /* in Sources */" for b_id in ios_sources])
ios_test_sources_entries = ",\n\t\t\t\t".join([f"{b_id} /* in Sources */" for b_id in ios_test_sources])
tv_test_sources_entries = ",\n\t\t\t\t".join([f"{b_id} /* in Sources */" for b_id in tv_test_sources])
tv_resources_entries = ",\n\t\t\t\t".join([f"{b_id} /* in Resources */" for b_id in tv_resources])
ios_resources_entries = ",\n\t\t\t\t".join([f"{b_id} /* in Resources */" for b_id in ios_resources])
tv_resources_phase_block = f"""\t\t{tv_resources_phase_id} /* Resources */ = {{
\t\t\tisa = PBXResourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t\t{tv_resources_entries},
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};""" if tv_resources else ""
ios_resources_phase_block = f"""\t\t{ios_resources_phase_id} /* Resources */ = {{
\t\t\tisa = PBXResourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t\t{ios_resources_entries},
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};""" if ios_resources else ""
tv_target_resources_phase_ref = f"\n\t\t\t\t{tv_resources_phase_id} /* Resources */," if tv_resources else ""
ios_target_resources_phase_ref = f"\n\t\t\t\t{ios_resources_phase_id} /* Resources */," if ios_resources else ""

# Targets
tv_target_id = gid("target_tv")
ios_target_id = gid("target_ios")
ios_test_target_id = gid("target_ios_tests")
tv_test_target_id = gid("target_tv_tests")
proj_id = gid("main_project")
main_group_id = gid("main_group")
products_group_id = gid("products_group")

# Test target <-> host app dependency wiring
ios_test_proxy_id = gid("ios_test_container_proxy")
ios_test_dep_id = gid("ios_test_target_dependency")
tv_test_proxy_id = gid("tv_test_container_proxy")
tv_test_dep_id = gid("tv_test_target_dependency")

# Configurations
tv_debug_config_id = gid("tv_debug_config")
tv_release_config_id = gid("tv_release_config")
tv_config_list_id = gid("tv_config_list")

ios_debug_config_id = gid("ios_debug_config")
ios_release_config_id = gid("ios_release_config")
ios_config_list_id = gid("ios_config_list")

ios_test_debug_config_id = gid("ios_test_debug_config")
ios_test_release_config_id = gid("ios_test_release_config")
ios_test_config_list_id = gid("ios_test_config_list")

tv_test_debug_config_id = gid("tv_test_debug_config")
tv_test_release_config_id = gid("tv_test_release_config")
tv_test_config_list_id = gid("tv_test_config_list")

proj_debug_config_id = gid("proj_debug_config")
proj_release_config_id = gid("proj_release_config")
proj_config_list_id = gid("proj_config_list")

pbxproj_content = f"""// !$*UTF8*$!
{{
	archiveVersion = 1;
	classes = {{
	}};
	objectVersion = 56;
	objects = {{

/* Begin PBXBuildFile section */
{chr(10).join(build_files)}
/* End PBXBuildFile section */

/* Begin PBXContainerItemProxy section */
		{ios_test_proxy_id} /* PBXContainerItemProxy */ = {{
			isa = PBXContainerItemProxy;
			containerPortal = {proj_id} /* Project object */;
			proxyType = 1;
			remoteGlobalIDString = {ios_target_id};
			remoteInfo = HDHROpeniOS;
		}};
		{tv_test_proxy_id} /* PBXContainerItemProxy */ = {{
			isa = PBXContainerItemProxy;
			containerPortal = {proj_id} /* Project object */;
			proxyType = 1;
			remoteGlobalIDString = {tv_target_id};
			remoteInfo = HDHROpenTV;
		}};
/* End PBXContainerItemProxy section */

/* Begin PBXFileReference section */
{chr(10).join(file_refs)}
/* End PBXFileReference section */

/* Begin PBXFrameworksBuildPhase section */
		{tv_frameworks_phase_id} /* Frameworks */ = {{
			isa = PBXFrameworksBuildPhase;
			buildActionMask = 2147483647;
			files = (
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
		{ios_frameworks_phase_id} /* Frameworks */ = {{
			isa = PBXFrameworksBuildPhase;
			buildActionMask = 2147483647;
			files = (
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
		{ios_test_frameworks_phase_id} /* Frameworks */ = {{
			isa = PBXFrameworksBuildPhase;
			buildActionMask = 2147483647;
			files = (
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
		{tv_test_frameworks_phase_id} /* Frameworks */ = {{
			isa = PBXFrameworksBuildPhase;
			buildActionMask = 2147483647;
			files = (
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
/* End PBXFrameworksBuildPhase section */

/* Begin PBXResourcesBuildPhase section */
{chr(10).join(b for b in [tv_resources_phase_block, ios_resources_phase_block] if b)}
/* End PBXResourcesBuildPhase section */

/* Begin PBXGroup section */
		{main_group_id} = {{
			isa = PBXGroup;
			children = (
				{gid("group_HDHROpenTV")} /* HDHROpenTV */,
				{gid("group_HDHROpeniOS")} /* HDHROpeniOS */,
				{gid("group_HDHROpeniOSTests")} /* HDHROpeniOSTests */,
				{gid("group_HDHROpenTVTests")} /* HDHROpenTVTests */,
				{products_group_id} /* Products */,
			);
			sourceTree = "<group>";
		}};
		{products_group_id} /* Products */ = {{
			isa = PBXGroup;
			children = (
				{tv_product_id} /* HDHROpenTV.app */,
				{ios_product_id} /* HDHROpeniOS.app */,
				{ios_test_product_id} /* HDHROpeniOSTests.xctest */,
				{tv_test_product_id} /* HDHROpenTVTests.xctest */,
			);
			name = Products;
			sourceTree = "<group>";
		}};
{chr(10).join(tv_groups)}
{chr(10).join(ios_groups)}
{chr(10).join(ios_test_groups)}
{chr(10).join(tv_test_groups)}
/* End PBXGroup section */

/* Begin PBXNativeTarget section */
		{tv_target_id} /* HDHROpenTV */ = {{
			isa = PBXNativeTarget;
			buildConfigurationList = {tv_config_list_id} /* Build configuration list for PBXNativeTarget "HDHROpenTV" */;
			buildPhases = (
				{tv_sources_phase_id} /* Sources */,
				{tv_frameworks_phase_id} /* Frameworks */,{tv_target_resources_phase_ref}
			);
			buildRules = (
			);
			dependencies = (
			);
			name = HDHROpenTV;
			packageProductDependencies = (
				{tv_pkg_dep_id} /* HDHROpenKit */,
			);
			productName = HDHROpenTV;
			productReference = {tv_product_id} /* HDHROpenTV.app */;
			productType = "com.apple.product-type.application";
		}};
		{ios_target_id} /* HDHROpeniOS */ = {{
			isa = PBXNativeTarget;
			buildConfigurationList = {ios_config_list_id} /* Build configuration list for PBXNativeTarget "HDHROpeniOS" */;
			buildPhases = (
				{ios_sources_phase_id} /* Sources */,
				{ios_frameworks_phase_id} /* Frameworks */,{ios_target_resources_phase_ref}
			);
			buildRules = (
			);
			dependencies = (
			);
			name = HDHROpeniOS;
			packageProductDependencies = (
				{ios_pkg_dep_id} /* HDHROpenKit */,
			);
			productName = HDHROpeniOS;
			productReference = {ios_product_id} /* HDHROpeniOS.app */;
			productType = "com.apple.product-type.application";
		}};
		{ios_test_target_id} /* HDHROpeniOSTests */ = {{
			isa = PBXNativeTarget;
			buildConfigurationList = {ios_test_config_list_id} /* Build configuration list for PBXNativeTarget "HDHROpeniOSTests" */;
			buildPhases = (
				{ios_test_sources_phase_id} /* Sources */,
				{ios_test_frameworks_phase_id} /* Frameworks */,
			);
			buildRules = (
			);
			dependencies = (
				{ios_test_dep_id} /* PBXTargetDependency */,
			);
			name = HDHROpeniOSTests;
			packageProductDependencies = (
				{ios_test_pkg_dep_id} /* HDHROpenKit */,
				{ios_viewinspector_dep_id} /* ViewInspector */,
			);
			productName = HDHROpeniOSTests;
			productReference = {ios_test_product_id} /* HDHROpeniOSTests.xctest */;
			productType = "com.apple.product-type.bundle.unit-test";
		}};
		{tv_test_target_id} /* HDHROpenTVTests */ = {{
			isa = PBXNativeTarget;
			buildConfigurationList = {tv_test_config_list_id} /* Build configuration list for PBXNativeTarget "HDHROpenTVTests" */;
			buildPhases = (
				{tv_test_sources_phase_id} /* Sources */,
				{tv_test_frameworks_phase_id} /* Frameworks */,
			);
			buildRules = (
			);
			dependencies = (
				{tv_test_dep_id} /* PBXTargetDependency */,
			);
			name = HDHROpenTVTests;
			packageProductDependencies = (
				{tv_test_pkg_dep_id} /* HDHROpenKit */,
				{tv_viewinspector_dep_id} /* ViewInspector */,
			);
			productName = HDHROpenTVTests;
			productReference = {tv_test_product_id} /* HDHROpenTVTests.xctest */;
			productType = "com.apple.product-type.bundle.unit-test";
		}};
/* End PBXNativeTarget section */

/* Begin PBXProject section */
		{proj_id} /* Project object */ = {{
			isa = PBXProject;
			attributes = {{
				BuildIndependentTargetsInParallel = 1;
				LastSwiftUpdateCheck = 1500;
				LastUpgradeCheck = 1500;
				TargetAttributes = {{
					{tv_target_id} = {{
						CreatedOnToolsVersion = 15.0;
					}};
					{ios_target_id} = {{
						CreatedOnToolsVersion = 15.0;
					}};
					{ios_test_target_id} = {{
						CreatedOnToolsVersion = 15.0;
						TestTargetID = {ios_target_id};
					}};
					{tv_test_target_id} = {{
						CreatedOnToolsVersion = 15.0;
						TestTargetID = {tv_target_id};
					}};
				}};
			}};
			buildConfigurationList = {proj_config_list_id} /* Build configuration list for PBXProject "HDHROpen" */;
			compatibilityVersion = "Xcode 14.0";
			developmentRegion = en;
			hasScannedForEncodings = 0;
			knownRegions = (
				en,
				Base,
			);
			mainGroup = {main_group_id};
			packageReferences = (
				{pkg_ref_id} /* XCLocalSwiftPackageReference "HDHROpenKit" */,
				{viewinspector_pkg_ref_id} /* XCRemoteSwiftPackageReference "ViewInspector" */,
			);
			productRefGroup = {products_group_id} /* Products */;
			projectDirPath = "";
			projectRoot = "";
			targets = (
				{tv_target_id} /* HDHROpenTV */,
				{tv_test_target_id} /* HDHROpenTVTests */,
				{ios_target_id} /* HDHROpeniOS */,
				{ios_test_target_id} /* HDHROpeniOSTests */,
			);
		}};
/* End PBXProject section */

/* Begin PBXSourcesBuildPhase section */
		{tv_sources_phase_id} /* Sources */ = {{
			isa = PBXSourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				{tv_sources_entries},
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
		{ios_sources_phase_id} /* Sources */ = {{
			isa = PBXSourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				{ios_sources_entries},
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
		{ios_test_sources_phase_id} /* Sources */ = {{
			isa = PBXSourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				{ios_test_sources_entries},
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
		{tv_test_sources_phase_id} /* Sources */ = {{
			isa = PBXSourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				{tv_test_sources_entries},
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
/* End PBXSourcesBuildPhase section */

/* Begin PBXTargetDependency section */
		{ios_test_dep_id} /* PBXTargetDependency */ = {{
			isa = PBXTargetDependency;
			target = {ios_target_id} /* HDHROpeniOS */;
			targetProxy = {ios_test_proxy_id} /* PBXContainerItemProxy */;
		}};
		{tv_test_dep_id} /* PBXTargetDependency */ = {{
			isa = PBXTargetDependency;
			target = {tv_target_id} /* HDHROpenTV */;
			targetProxy = {tv_test_proxy_id} /* PBXContainerItemProxy */;
		}};
/* End PBXTargetDependency section */

/* Begin XCBuildConfiguration section */
		{proj_debug_config_id} /* Debug */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				ALWAYS_SEARCH_USER_PATHS = NO;
				CLANG_ANALYZER_NONNULL = YES;
				CLANG_CXX_LANGUAGE_STANDARD = "gnu++20";
				CLANG_ENABLE_MODULES = YES;
				CLANG_ENABLE_OBJC_ARC = YES;
				COPY_PHASE_STRIP = NO;
				DEBUG_INFORMATION_FORMAT = dwarf;
				ENABLE_STRICT_OBJC_MSGSEND = YES;
				ENABLE_TESTABILITY = YES;
				GCC_DYNAMIC_NO_PIC = NO;
				GCC_NO_COMMON_BLOCKS = YES;
				GCC_OPTIMIZATION_LEVEL = 0;
				GCC_PREPROCESSOR_DEFINITIONS = (
					"DEBUG=1",
					"$(inherited)",
				);
				GCC_WARN_64_TO_32_BIT_CONVERSION = YES;
				GCC_WARN_ABOUT_RETURN_TYPE = YES_ERROR;
				GCC_WARN_UNDEFINED_VARIABLES = YES;
				GCC_WARN_UNINITIALIZED_AUTOS = YES_AGGRESSIVE;
				MTL_ENABLE_DEBUG_INFO = INCLUDE_SOURCE;
				MTL_FAST_MATH = YES;
				ONLY_ACTIVE_ARCH = YES;
				SWIFT_ACTIVE_COMPILATION_CONDITIONS = "DEBUG $(inherited)";
				SWIFT_OPTIMIZATION_LEVEL = "-Onone";
				SWIFT_VERSION = 5.0;
			}};
			name = Debug;
		}};
		{proj_release_config_id} /* Release */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				ALWAYS_SEARCH_USER_PATHS = NO;
				CLANG_ANALYZER_NONNULL = YES;
				CLANG_CXX_LANGUAGE_STANDARD = "gnu++20";
				CLANG_ENABLE_MODULES = YES;
				CLANG_ENABLE_OBJC_ARC = YES;
				COPY_PHASE_STRIP = NO;
				DEBUG_INFORMATION_FORMAT = "dwarf-with-dsym";
				ENABLE_NS_ASSERTIONS = NO;
				ENABLE_STRICT_OBJC_MSGSEND = YES;
				GCC_NO_COMMON_BLOCKS = YES;
				GCC_WARN_64_TO_32_BIT_CONVERSION = YES;
				GCC_WARN_ABOUT_RETURN_TYPE = YES_ERROR;
				GCC_WARN_UNDEFINED_VARIABLES = YES;
				GCC_WARN_UNINITIALIZED_AUTOS = YES_AGGRESSIVE;
				MTL_ENABLE_DEBUG_INFO = NO;
				MTL_FAST_MATH = YES;
				SWIFT_COMPILATION_MODE = wholemodule;
				SWIFT_OPTIMIZATION_LEVEL = "-O";
				SWIFT_VERSION = 5.0;
			}};
			name = Release;
		}};
		{tv_debug_config_id} /* Debug */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				ASSETCATALOG_COMPILER_APPICON_NAME = "App Icon & Top Shelf Image";
				CODE_SIGN_ENTITLEMENTS = HDHROpenTV/HDHROpenTV.entitlements;
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = HDHROpenTV/Resources/Info.plist;
				INFOPLIST_KEY_CFBundleDisplayName = "HDHR Open";
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = org.hdhropen.client.tv;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = appletvos;
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = 3;
				TVOS_DEPLOYMENT_TARGET = 17.0;
			}};
			name = Debug;
		}};
		{tv_release_config_id} /* Release */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				ASSETCATALOG_COMPILER_APPICON_NAME = "App Icon & Top Shelf Image";
				CODE_SIGN_ENTITLEMENTS = HDHROpenTV/HDHROpenTV.entitlements;
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = HDHROpenTV/Resources/Info.plist;
				INFOPLIST_KEY_CFBundleDisplayName = "HDHR Open";
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = org.hdhropen.client.tv;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = appletvos;
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = 3;
				TVOS_DEPLOYMENT_TARGET = 17.0;
			}};
			name = Release;
		}};
		{ios_debug_config_id} /* Debug */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
				CODE_SIGN_ENTITLEMENTS = HDHROpeniOS/HDHROpeniOS.entitlements;
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = HDHROpeniOS/Resources/Info.plist;
				INFOPLIST_KEY_CFBundleDisplayName = "HDHR Open";
				IPHONEOS_DEPLOYMENT_TARGET = 18.0;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = org.hdhropen.client.ios;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = iphoneos;
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = "1,2";
			}};
			name = Debug;
		}};
		{ios_release_config_id} /* Release */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
				CODE_SIGN_ENTITLEMENTS = HDHROpeniOS/HDHROpeniOS.entitlements;
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = HDHROpeniOS/Resources/Info.plist;
				INFOPLIST_KEY_CFBundleDisplayName = "HDHR Open";
				IPHONEOS_DEPLOYMENT_TARGET = 18.0;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = org.hdhropen.client.ios;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = iphoneos;
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = "1,2";
			}};
			name = Release;
		}};
		{ios_test_debug_config_id} /* Debug */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				BUNDLE_LOADER = "$(TEST_HOST)";
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = YES;
				IPHONEOS_DEPLOYMENT_TARGET = 18.0;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
					"@loader_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = org.hdhropen.client.ios.tests;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = iphoneos;
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = "1,2";
				TEST_HOST = "$(BUILT_PRODUCTS_DIR)/HDHROpeniOS.app/HDHROpeniOS";
			}};
			name = Debug;
		}};
		{ios_test_release_config_id} /* Release */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				BUNDLE_LOADER = "$(TEST_HOST)";
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = YES;
				IPHONEOS_DEPLOYMENT_TARGET = 18.0;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
					"@loader_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = org.hdhropen.client.ios.tests;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = iphoneos;
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = "1,2";
				TEST_HOST = "$(BUILT_PRODUCTS_DIR)/HDHROpeniOS.app/HDHROpeniOS";
			}};
			name = Release;
		}};
		{tv_test_debug_config_id} /* Debug */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				BUNDLE_LOADER = "$(TEST_HOST)";
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = YES;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
					"@loader_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = org.hdhropen.client.tv.tests;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = appletvos;
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = 3;
				TEST_HOST = "$(BUILT_PRODUCTS_DIR)/HDHROpenTV.app/HDHROpenTV";
				TVOS_DEPLOYMENT_TARGET = 17.0;
			}};
			name = Debug;
		}};
		{tv_test_release_config_id} /* Release */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
				BUNDLE_LOADER = "$(TEST_HOST)";
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = YES;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
					"@loader_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = org.hdhropen.client.tv.tests;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = appletvos;
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = 3;
				TEST_HOST = "$(BUILT_PRODUCTS_DIR)/HDHROpenTV.app/HDHROpenTV";
				TVOS_DEPLOYMENT_TARGET = 17.0;
			}};
			name = Release;
		}};
/* End XCBuildConfiguration section */

/* Begin XCConfigurationList section */
		{proj_config_list_id} /* Build configuration list for PBXProject "HDHROpen" */ = {{
			isa = XCConfigurationList;
			buildConfigurations = (
				{proj_debug_config_id} /* Debug */,
				{proj_release_config_id} /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		}};
		{tv_config_list_id} /* Build configuration list for PBXNativeTarget "HDHROpenTV" */ = {{
			isa = XCConfigurationList;
			buildConfigurations = (
				{tv_debug_config_id} /* Debug */,
				{tv_release_config_id} /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		}};
		{ios_config_list_id} /* Build configuration list for PBXNativeTarget "HDHROpeniOS" */ = {{
			isa = XCConfigurationList;
			buildConfigurations = (
				{ios_debug_config_id} /* Debug */,
				{ios_release_config_id} /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		}};
		{ios_test_config_list_id} /* Build configuration list for PBXNativeTarget "HDHROpeniOSTests" */ = {{
			isa = XCConfigurationList;
			buildConfigurations = (
				{ios_test_debug_config_id} /* Debug */,
				{ios_test_release_config_id} /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		}};
		{tv_test_config_list_id} /* Build configuration list for PBXNativeTarget "HDHROpenTVTests" */ = {{
			isa = XCConfigurationList;
			buildConfigurations = (
				{tv_test_debug_config_id} /* Debug */,
				{tv_test_release_config_id} /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		}};
/* End XCConfigurationList section */

/* Begin XCLocalSwiftPackageReference section */
		{pkg_ref_id} /* HDHROpenKit */ = {{
			isa = XCLocalSwiftPackageReference;
			relativePath = HDHROpenKit;
		}};
/* End XCLocalSwiftPackageReference section */

/* Begin XCRemoteSwiftPackageReference section */
		{viewinspector_pkg_ref_id} /* XCRemoteSwiftPackageReference "ViewInspector" */ = {{
			isa = XCRemoteSwiftPackageReference;
			repositoryURL = "https://github.com/nalexn/ViewInspector";
			requirement = {{
				kind = upToNextMajorVersion;
				minimumVersion = 0.9.0;
			}};
		}};
/* End XCRemoteSwiftPackageReference section */

/* Begin XCSwiftPackageProductDependency section */
		{tv_pkg_dep_id} /* HDHROpenKit */ = {{
			isa = XCSwiftPackageProductDependency;
			package = {pkg_ref_id} /* HDHROpenKit */;
			productName = HDHROpenKit;
		}};
		{ios_pkg_dep_id} /* HDHROpenKit */ = {{
			isa = XCSwiftPackageProductDependency;
			package = {pkg_ref_id} /* HDHROpenKit */;
			productName = HDHROpenKit;
		}};
		{ios_test_pkg_dep_id} /* HDHROpenKit */ = {{
			isa = XCSwiftPackageProductDependency;
			package = {pkg_ref_id} /* HDHROpenKit */;
			productName = HDHROpenKit;
		}};
		{tv_test_pkg_dep_id} /* HDHROpenKit */ = {{
			isa = XCSwiftPackageProductDependency;
			package = {pkg_ref_id} /* HDHROpenKit */;
			productName = HDHROpenKit;
		}};
		{ios_viewinspector_dep_id} /* ViewInspector */ = {{
			isa = XCSwiftPackageProductDependency;
			package = {viewinspector_pkg_ref_id} /* XCRemoteSwiftPackageReference "ViewInspector" */;
			productName = ViewInspector;
		}};
		{tv_viewinspector_dep_id} /* ViewInspector */ = {{
			isa = XCSwiftPackageProductDependency;
			package = {viewinspector_pkg_ref_id} /* XCRemoteSwiftPackageReference "ViewInspector" */;
			productName = ViewInspector;
		}};
/* End XCSwiftPackageProductDependency section */

	}};
	rootObject = {proj_id} /* Project object */;
}}
"""

PROJECT_FILE.write_text(pbxproj_content)
print(f"Generated {PROJECT_FILE}")

# Generate Shared Schemes
def create_scheme(target_id, target_name, test_target_id, test_target_name, is_tvos=False):
    scheme_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Scheme
   LastUpgradeVersion = "1500"
   version = "1.7">
   <BuildAction
      parallelizeBuildables = "YES"
      buildImplicitDependencies = "YES">
      <BuildActionEntries>
         <BuildActionEntry
            buildForTesting = "YES"
            buildForRunning = "YES"
            buildForProfiling = "YES"
            buildForArchiving = "YES"
            buildForAnalyzing = "YES">
            <BuildableReference
               BuildableIdentifier = "primary"
               BlueprintIdentifier = "{target_id}"
               BuildableName = "{target_name}.app"
               BlueprintName = "{target_name}"
               ReferencedContainer = "container:HDHROpen.xcodeproj">
            </BuildableReference>
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <TestAction
      buildConfiguration = "Debug"
      selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB"
      selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB"
      shouldUseLaunchSchemeArgsEnv = "YES">
      <Testables>
         <TestableReference
            skipped = "NO">
            <BuildableReference
               BuildableIdentifier = "primary"
               BlueprintIdentifier = "{test_target_id}"
               BuildableName = "{test_target_name}.xctest"
               BlueprintName = "{test_target_name}"
               ReferencedContainer = "container:HDHROpen.xcodeproj">
            </BuildableReference>
         </TestableReference>
      </Testables>
   </TestAction>
   <LaunchAction
      buildConfiguration = "Debug"
      selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB"
      selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB"
      launchStyle = "0"
      useCustomWorkingDirectory = "NO"
      ignoresPersistentStateOnLaunch = "NO"
      debugDocumentVersioning = "YES"
      debugServiceExtension = "internal"
      allowLocationSimulation = "YES">
      <BuildableProductRunnable
         runnableDebuggingMode = "0">
         <BuildableReference
            BuildableIdentifier = "primary"
            BlueprintIdentifier = "{target_id}"
            BuildableName = "{target_name}.app"
            BlueprintName = "{target_name}"
            ReferencedContainer = "container:HDHROpen.xcodeproj">
         </BuildableReference>
      </BuildableProductRunnable>
   </LaunchAction>
   <ProfileAction
      buildConfiguration = "Release"
      shouldUseLaunchSchemeArgsEnv = "YES"
      savedToolIdentifier = ""
      useCustomWorkingDirectory = "NO"
      debugDocumentVersioning = "YES">
      <BuildableProductRunnable
         runnableDebuggingMode = "0">
         <BuildableReference
            BuildableIdentifier = "primary"
            BlueprintIdentifier = "{target_id}"
            BuildableName = "{target_name}.app"
            BlueprintName = "{target_name}"
            ReferencedContainer = "container:HDHROpen.xcodeproj">
         </BuildableReference>
      </BuildableProductRunnable>
   </ProfileAction>
   <AnalyzeAction
      buildConfiguration = "Debug">
   </AnalyzeAction>
   <ArchiveAction
      buildConfiguration = "Release"
      revealArchiveInOrganizer = "YES">
   </ArchiveAction>
</Scheme>
"""
    scheme_file = SCHEMES_DIR / f"{target_name}.xcscheme"
    scheme_file.write_text(scheme_content)
    print(f"Generated {scheme_file}")

create_scheme(tv_target_id, "HDHROpenTV", tv_test_target_id, "HDHROpenTVTests", is_tvos=True)
create_scheme(ios_target_id, "HDHROpeniOS", ios_test_target_id, "HDHROpeniOSTests", is_tvos=False)
