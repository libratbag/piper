project('piper',
    version: '0.8',
    license: 'GPL-2.0-or-later',
    meson_version: '>= 0.51.0')
# The tag date of the project_version(), update when the version bumps.
version_date='2024-09-24'

# The DBus API version of ratbagd that we are compatible with. Anything
# higher or lower will not be compatible so make sure you bumpt that to the
# latest released ratbagd version whenever a piper release is made.
ratbagd_api_version = 2


# Options
enable_runtime_dependency_checks = get_option('runtime-dependency-checks')
enable_formatting = get_option('format-code')
enable_linting = get_option('lint-code')

# Dependencies
if enable_runtime_dependency_checks
    ratbagd = find_program('ratbagd', required: false)
    ratbagd_required_version='0.18'

    if not ratbagd.found()
        message('''
        ************************ ERROR ***********************
        * _???_     Dependency libratbag not found in $PATH! *
        *(_)_(_)    ratbagd must be installed and running    *
        * (o o)     for Piper to work.                       *
        *==\o/==                                             *
        ******************************************************
        ''')
    else
        r = run_command(ratbagd, '--version')
        if r.returncode() != 0 or r.stdout().version_compare('<' + ratbagd_required_version)
            error('''
            ************************ ERROR *****************************
            *                 (   )(                                   *
            *         (\-.     ) (  )    ratbagd found in $PATH is too *
            *         / _`> .---------.  old and  will  not  work with *
            * _)     / _)=  |'-------'|  this version of Piper. Please *
            *(      / _/    |O   O   o|  update libratbag/ratbagd.     *
            * `-.__(___)_   | o O . o |                                *
            ************************************************************
            ''')
        endif
    endif

    # external python modules that are required for running piper
    python_modules = [
        'lxml',
        'evdev',
        'cairo',
        'gi',
    ]

    dependency('pygobject-3.0', required: true)
else
    # external python modules that are required for building piper
    python_modules = ['lxml']
endif

# Gtk version required
gtk_major_version = 3
gtk_minor_version = 22

prefix = get_option('prefix')
datadir = join_paths(prefix, get_option('datadir'))
localedir = join_paths(prefix, get_option('localedir'))
pkgdatadir = join_paths(datadir, meson.project_name())
bindir = join_paths(prefix, get_option('bindir'))
podir = join_paths(meson.current_source_dir(), 'po')
mandir = join_paths(prefix, get_option('mandir'))

i18n = import('i18n')

subdir('data')
subdir('po')

# Find the directory to install our Python code
pymod = import('python')
py3 = pymod.find_installation(modules: python_modules)
python_dir = py3.get_install_dir()
install_subdir('piper',
               install_dir: python_dir,
               exclude_directories: '__pycache__')

config_piper = configuration_data()
config_piper.set('pkgdatadir', pkgdatadir)
config_piper.set('localedir', localedir)
config_piper.set('gtk_major_version', gtk_major_version)
config_piper.set('gtk_minor_version', gtk_minor_version)
config_piper.set('RATBAGD_API_VERSION', ratbagd_api_version)
config_piper.set('devel', '')

config_piper_devel = config_piper
config_piper_devel.set('pkgdatadir', join_paths(meson.current_build_dir(), 'data'))
config_piper_devel.set('localedir', join_paths(meson.current_build_dir(), 'po'))
config_piper_devel.set('devel', '''
sys.path.insert(1, '@0@')
print('Running from source tree, using local files')
'''.format(meson.current_source_dir()))

configure_file(input: 'piper.in',
               output: 'piper',
               configuration: config_piper,
               install_dir: bindir)

configure_file(input: 'piper.in',
               output: 'piper.devel',
               configuration: config_piper_devel)

if meson.version().version_compare('>=0.59.0')
    gnome.post_install(
        gtk_update_icon_cache: true,
        update_desktop_database: true
    )
else
    meson.add_install_script('meson_install.sh')
endif

env_test = environment()
# See: https://github.com/mesonbuild/meson/issues/3306.
env_test.set('MESON_SOURCE_ROOT', meson.current_source_dir())

test_svg_files = find_program('tests/check-svg.py')
test(
  'check-svg',
  test_svg_files,
  args : join_paths(meson.current_source_dir(), 'data/svgs/'),
  env : ['BASEDIR=@0@'.format(join_paths(meson.current_source_dir(), 'data/'))],
)

test(
  'svg-lookup-check',
  find_program('tests/svg-lookup-ini-test.py'),
  args : [svg_mapping, join_paths(meson.current_source_dir(), 'data/svgs/')],
)

test(
  'files-in-git',
  find_program('tests/check-files-in-git.sh'),
  args : [meson.current_source_dir()],
  suite : ['all'],
)

#### code formatting #####
if enable_formatting
    run_target(
      'python-black',
      command : 'tools/python-black.sh',
    )

    python_black_check = find_program(join_paths(meson.current_source_dir(), 'tests/python-black-check.sh'))
    run_target(
      'python-black-check',
      command : python_black_check,
    )
    test(
      'python-black-check',
      python_black_check,
      env: env_test,
    )
endif

if enable_linting
    #### code linting #####
    run_target(
      'python-ruff',
      command : 'tools/python-ruff.sh',
    )

    python_ruff_check = find_program(join_paths(meson.current_source_dir(), 'tests/python-ruff-check.sh'))
    run_target(
      'python-ruff-check',
      command : python_ruff_check,
    )
    test(
      'python-ruff-check',
      python_ruff_check,
      env: env_test,
    )
endif
