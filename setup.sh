if [ $# -eq 0 ]; then
    setupPath="/usr/local/bin"
else
    setupPath=$1
fi

pip install hachoir-metadata
pip install hachoir-core
pip install hachoir-parser

python createConfig.py ${setupPath}

mkdir -p ${setupPath}/TBFS/

cp tag ${setupPath}/
chmod +x ${setupPath}/tag

cp tagfs ${setupPath}/
chmod +x ${setupPath}/tagfs


cp getfiles ${setupPath}/
chmod +x ${setupPath}/getfiles 

cp lstag ${setupPath}/
chmod +x ${setupPath}/lstag 

cp config.json ${setupPath}/TBFS/
cp pythonInterface.py ${setupPath}/TBFS/
cp fuse_start.py ${setupPath}/TBFS/

