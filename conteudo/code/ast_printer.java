import com.github.javaparser.*;
import com.github.javaparser.ast.*;
import com.github.javaparser.printer.*;

import java.io.*;
import java.util.*;

public class ast_printer {

    public static void main(String[] args) throws Exception {
        String file_path = args[0];
        CompilationUnit cu = StaticJavaParser.parse(new File(file_path));
        DotPrinter printer = new DotPrinter(true);
        try (FileWriter fileWriter = new FileWriter(file_path + "_ast.dot");
                PrintWriter printWriter = new PrintWriter(fileWriter)) {
            printWriter.print(printer.output(cu));
        }
    }
}
