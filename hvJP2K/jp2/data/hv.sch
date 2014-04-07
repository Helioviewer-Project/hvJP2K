<?xml version="1.0" encoding="UTF-8"?>
<!--
	HelioViewer File Format Verification Facility (HVFFVF)
	v0.2 preliminary

	$Id$
-->
<schema xmlns="http://purl.oclc.org/dsdl/schematron" queryBinding="xslt" schemaVersion="iso">
	<title>Check for HV JP2 compliance</title>
	<pattern>
		<!-- checks on jpylyzer output -->
		<!-- check presence of jpylyzer element -->
		<rule context="/">
			<assert test="jpylyzer">no jpylyzer element found</assert>
		</rule>
		<!-- check presence of isValidJP2 element with the text 'True' -->
		<rule context="/jpylyzer">
			<assert test="isValidJP2 = 'True'">not valid JP2</assert>
		</rule>
		<!-- check jpylyzer validation of xmlBox if there -->
		<rule context="/jpylyzer/tests/xmlBox">
			<assert test="containsWellformedXML != 'False'">malformed XML metadata</assert>
		</rule>
		<!-- checks presence and structure of xmlBox element -->
		<!-- context="/jpylyzer" -->
		<rule context="properties">
			<assert test="xmlBox">no XML box</assert>
		</rule>
		<rule context="properties/xmlBox">
			<assert test="meta">meta missing</assert>
			<assert test="meta/fits">meta/fits missing</assert>
			<assert test="meta/helioviewer">meta/helioviewer missing</assert>
		</rule>
		<!-- checks on XML metadata -->
		<!-- context="/jpylyzer/properties/xmlBox/meta" -->
		<!-- old style -->
		<rule context="fits">
			<!-- dataset id -->
			<assert test="TELESCOP">keyword missing: TELESCOP</assert>
			<assert test="INSTRUME">keyword missing: INSTRUME</assert>
			<assert test="WAVELNTH">keyword missing: WAVELNTH</assert>
			<!-- obs & WCS -->
			<assert test="DATE-OBS">keyword missing: DATE-OBS</assert>
			<assert test="DSUN_OBS">keyword missing: DSUN_OBS</assert>
			<assert test="CDELT1">keyword missing: CDELT1</assert>
			<assert test="CDELT2">keyword missing: CDELT2</assert>
			<assert test="CRPIX1">keyword missing: CRPIX1</assert>
			<assert test="CRPIX2">keyword missing: CRPIX2</assert>
		</rule>
		<!-- filename check -->
		<rule context="fits">
			<let name="date-obs" value="replace(translate(substring-before(DATE-OBS, '.'), '-:', '__'), 'T', '__')"/>
			<let name="telescop" value="replace(TELESCOP, '/', '_')"/>
			<let name="invalid-detector" value="INSTRUME = 'SWAP' or not(DETECTOR)"/>
			<let name="detector" value="concat(substring(INSTRUME, 1, invalid-detector * string-length(INSTRUME)), substring(DETECTOR, 1, not(invalid-detector) * string-length(DETECTOR)))"/>
			<let name="filename" value="concat($date-obs, '_', $telescop, '_', INSTRUME, '_', $detector, '_', WAVELNTH, '.jp2')"/>
			<assert test="$filename = /jpylyzer/fileInfo/fileName">invalid filename</assert>
		</rule>
		<!-- checks on codestream parameters -->
		<!-- context="/jpylyzer/properties/contiguousCodestreamBox" -->
		<!-- SIZ -->
		<rule context="siz">
			<!-- single tile -->
			<assert test="numberOfTiles = 1">tiled image</assert>
		</rule>
		<!-- COD -->
		<rule context="cod">
			<!-- precincts -->
			<assert test="precincts = 'yes'">no precincts</assert>
			<assert test="precincts != 'yes' or precinctSizeX &gt; 127">invalid precinct X size</assert>
			<assert test="precincts != 'yes' or precinctSizeY &gt; 127">invalid precinct Y size</assert>
			<!-- progression order -->
			<assert test="order = 'RPCL'">wrong progression order</assert>
		</rule>
		<!-- tiles -->
		<rule context="tileParts">
			<!-- PLT markers -->
			<assert test="tilePart/plt">missing PLT markers</assert>
		</rule>
	</pattern>
</schema>
