#include "ROOT/RDataFrame.hxx"
#include <stdio.h>
#include <iostream>
#include <filesystem>

void add_fWeight(const char* infile, double simcnorm) {
    try {
        ROOT::RDataFrame df("h10", infile);

        auto df_new = df.Define("fWeight", [simcnorm](float Weight) {
            return Weight * simcnorm;
        }, {"Weight"});

        std::filesystem::path inpath(infile);
        std::string outfile = (inpath.parent_path() / ("wfWeight_" + inpath.filename().string())).string();

        df_new.Snapshot("h10", outfile.c_str());
        std::cout << "Modified ROOT file including fWeight: " << outfile << std::endl;

    }
    catch (const std::exception& e) {
        std::cerr << "ERROR: Couldn't add the fWeight branch: " << e.what() << std::endl;
    }
}