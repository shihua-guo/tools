package com.dbdoctor;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ConfigLoader {
    private ConfigLoader() {
    }

    public static DoctorConfig load(Path path) throws IOException {
        if (path == null || !Files.isRegularFile(path)) {
            throw new IllegalArgumentException("config file does not exist: " + path);
        }
        ObjectMapper mapper = new ObjectMapper(new YAMLFactory());
        DoctorConfig config = mapper.readValue(path.toFile(), DoctorConfig.class);
        config.normalize();
        config.validate();
        return config;
    }
}
