<?xml version="1.0" encoding="UTF-8"?>
<!--
    HelioViewer File Format Verification Facility (HVFFVF)
    v0.3 for jpylyzer 2.2
-->
<iso:schema xmlns="http://purl.oclc.org/dsdl/schematron" xmlns:iso="http://purl.oclc.org/dsdl/schematron" queryBinding="xslt" schemaVersion="iso">
    <iso:title>Check for HV JP2 compliance</iso:title>
    <iso:pattern>
        <!-- checks on jpylyzer output -->
        <!-- check presence of the single-file jpylyzer result -->
        <iso:rule context="/">
            <iso:assert test="file">no file element found</iso:assert>
        </iso:rule>
        <iso:rule context="/file">
            <iso:assert test="isValid[@format = 'jp2'] = 'True'">not valid JP2</iso:assert>
        </iso:rule>
        <!-- check jpylyzer validation of xmlBox if there -->
        <iso:rule context="/file/tests/xmlBox">
            <iso:assert test="containsWellformedXML != 'False'">malformed XML metadata</iso:assert>
        </iso:rule>
        <!-- checks presence and structure of xmlBox element -->
        <iso:rule context="/file/properties">
            <iso:assert test="xmlBox">no XML box</iso:assert>
        </iso:rule>
        <iso:rule context="/file/properties/xmlBox">
            <iso:assert test="meta">meta missing</iso:assert>
            <iso:assert test="meta/fits">meta/fits missing</iso:assert>
            <iso:assert test="meta/helioviewer">meta/helioviewer missing</iso:assert>
        </iso:rule>
        <!-- checks on XML metadata -->
        <iso:rule context="/file/properties/xmlBox/meta/fits">
            <!-- dataset id -->
            <iso:assert test="TELESCOP">keyword missing: TELESCOP</iso:assert>
            <iso:assert test="INSTRUME">keyword missing: INSTRUME</iso:assert>
            <iso:assert test="WAVELNTH">keyword missing: WAVELNTH</iso:assert>
            <!-- obs & WCS -->
            <iso:assert test="DATE-OBS">keyword missing: DATE-OBS</iso:assert>
            <iso:assert test="DSUN_OBS">keyword missing: DSUN_OBS</iso:assert>
            <iso:assert test="CDELT1">keyword missing: CDELT1</iso:assert>
            <iso:assert test="CDELT2">keyword missing: CDELT2</iso:assert>
            <iso:assert test="CRPIX1">keyword missing: CRPIX1</iso:assert>
            <iso:assert test="CRPIX2">keyword missing: CRPIX2</iso:assert>
            <!-- Current producers store the JP2 basename in FILENAME. Older
                 products may identify the source FITS file instead. -->
            <iso:assert test="not(substring(FILENAME, string-length(FILENAME) - 3) = '.jp2') or FILENAME = /file/fileInfo/fileName">invalid filename</iso:assert>
        </iso:rule>
        <!-- checks on codestream parameters -->
        <!-- SIZ -->
        <iso:rule context="/file/properties/contiguousCodestreamBox/siz">
            <!-- single tile -->
            <iso:assert test="numberOfTiles = 1">tiled image</iso:assert>
        </iso:rule>
        <!-- COD -->
        <iso:rule context="/file/properties/contiguousCodestreamBox/cod">
            <!-- precincts -->
            <iso:assert test="precincts = 'user defined'">no precincts</iso:assert>
            <iso:assert test="not(precinctSizeX &lt; 128)">invalid precinct X size</iso:assert>
            <iso:assert test="not(precinctSizeY &lt; 128)">invalid precinct Y size</iso:assert>
            <!-- progression order -->
            <iso:assert test="order = 'RPCL'">wrong progression order</iso:assert>
        </iso:rule>
        <!-- tiles -->
        <iso:rule context="/file/properties/contiguousCodestreamBox/tileParts">
            <!-- PLT markers -->
            <iso:assert test="tilePart/pltCount &gt; 0">missing PLT markers</iso:assert>
        </iso:rule>
    </iso:pattern>
</iso:schema>
